"""Administrator-defined evidence queries, independent of business database schema."""
import json
import os
import re
import sqlite3
import time
from pathlib import Path


class SourceError(ValueError):
    pass


def load_sources(config):
    if not config.data_sources_file:return []
    path=Path(config.data_sources_file).resolve()
    if path.stat().st_size>200000:raise SourceError('Data source configuration exceeds limit')
    data=json.loads(path.read_text('utf-8'))
    validate_sources(data)
    for source in data['sources']:
        if source['driver']=='sqlite':source['path']=str((path.parent/source['path']).resolve())
    return data['sources']


def validate_sources(data):
    if not isinstance(data,dict) or set(data)!={'version','sources'} or data['version']!=1 or not isinstance(data['sources'],list) or len(data['sources'])>20:
        raise SourceError('Invalid data source document')
    names=set();source_ids=set()
    for source in data['sources']:
        if not isinstance(source,dict) or set(source)-{'id','driver','path','dsn_env','queries','timeout_seconds','max_rows','tables','schema_notes'}:
            raise SourceError('Invalid source settings')
        if source.get('driver') not in {'sqlite','postgresql'}:raise SourceError('Supported source drivers: sqlite, postgresql')
        if not re.fullmatch(r'[a-z][a-z0-9_]{1,40}',source.get('id','')):raise SourceError('Invalid source ID')
        if source['id'] in source_ids:raise SourceError('Source IDs must be unique')
        source_ids.add(source['id'])
        if source['driver']=='sqlite' and (not isinstance(source.get('path'),str) or not source['path']):raise SourceError('SQLite source needs a path')
        if source['driver']=='postgresql' and not re.fullmatch(r'[A-Z][A-Z0-9_]{1,100}',source.get('dsn_env','')):raise SourceError('PostgreSQL source needs a credential environment variable name')
        for key,default,maximum in [('timeout_seconds',5,30),('max_rows',20,100)]:
            value=source.get(key,default)
            if type(value) is not int or not 1<=value<=maximum:raise SourceError('Invalid source limit')
        if source['driver']=='sqlite' and (not isinstance(source.get('tables'),list) or not source['tables'] or any(not isinstance(t,str) or not re.fullmatch(r'[A-Za-z_]\w*',t) for t in source['tables'])):raise SourceError('Declare approved tables or views')
        if source['driver']=='postgresql' and 'tables' in source:raise SourceError('PostgreSQL table access must be configured through database role privileges, not a tables list')
        if not isinstance(source.get('schema_notes',''),str) or len(source.get('schema_notes',''))>4000:raise SourceError('Invalid schema description')
        if not isinstance(source.get('queries'),list) or not source['queries'] or len(source['queries'])>30:raise SourceError('Source needs approved queries')
        for q in source['queries']:
            if not isinstance(q,dict) or set(q)-{'name','description','sql','parameters','required','mode','when','title','require_rows'}:raise SourceError('Invalid query definition')
            name=q.get('name','')
            if not re.fullmatch(r'[a-z][a-z0-9_]{1,63}',name) or name in names:raise SourceError('Query names must be unique tool names')
            names.add(name)
            if not isinstance(q.get('description'),str) or not 1<=len(q['description'])<=2000:raise SourceError('Describe the query purpose and parameter meaning')
            if q.get('mode','auto') not in {'auto','required','conditional','off'}:raise SourceError('Invalid query mode')
            if q.get('mode')=='conditional' and not q.get('when'):raise SourceError('Conditional query needs a semantic applicability description')
            sql=q.get('sql','')
            if not isinstance(sql,str) or len(sql)>12000 or not re.match(r'^\s*(SELECT|WITH)\b',sql,re.I) or ';' in sql:raise SourceError('Use one approved SELECT or WITH query')
            params=q.get('parameters',{})
            if not isinstance(params,dict) or len(params)>20:raise SourceError('Invalid query parameters')
            for key,spec in params.items():
                if not re.fullmatch(r'[a-z][a-z0-9_]{0,40}',key) or not isinstance(spec,dict) or spec.get('type') not in {'string','integer','boolean'}:raise SourceError('Use named scalar query parameters')
            if not isinstance(q.get('required',[]),list) or not set(q.get('required',[]))<=set(params):raise SourceError('Invalid required parameters')
            if 'require_rows' in q and type(q['require_rows']) is not bool:raise SourceError('Invalid row requirement')
    if len(names)>60:raise SourceError('Too many evidence queries')
    return data


def normalize(rows,columns,max_rows):
    truncated=len(rows)>max_rows
    records=[]
    for row in rows[:max_rows]:
        record={}
        for key,value in zip(columns,row):
            if isinstance(value,bytes):raise SourceError('Binary data is not an evidence column')
            if value is not None and not isinstance(value,(str,int,float,bool)):value=str(value)
            if isinstance(value,str) and len(value)>8000:raise SourceError('Evidence cell exceeds limit; narrow the query')
            record[key]=value
        records.append(record)
    result={'rows':records,'truncated':truncated,'available':not truncated}
    if len(json.dumps(result,ensure_ascii=False).encode())>16000:raise SourceError('Evidence result exceeds limit; narrow the query')
    return result


def execute_query(source,query,arguments):
    limit=source.get('max_rows',20);timeout=source.get('timeout_seconds',5)
    parameters={k:arguments.get(k) for k in query.get('parameters',{})}
    try:
        if source['driver']=='sqlite':
            uri=Path(source['path']).resolve().as_uri()+'?mode=ro'
            connection=sqlite3.connect(uri,uri=True,timeout=timeout)
            try:
                connection.execute('PRAGMA query_only=ON')
                if hasattr(connection,"enable_load_extension"): connection.enable_load_extension(False)
                deadline=time.monotonic()+timeout
                connection.set_progress_handler(lambda: int(time.monotonic()>deadline),1000)
                allowed_functions={'count','sum','avg','min','max','lower','upper','length','coalesce','ifnull','nullif','trim','ltrim','rtrim','substr','substring','round','abs','date','datetime','julianday','strftime','like','glob'}
                tables=set(source['tables'])
                def authorize(action,arg1,arg2,database,trigger):
                    if action in {sqlite3.SQLITE_SELECT,sqlite3.SQLITE_RECURSIVE}:return sqlite3.SQLITE_OK
                    if action==sqlite3.SQLITE_READ and database=='main' and arg1 in tables:return sqlite3.SQLITE_OK
                    if action==sqlite3.SQLITE_FUNCTION and (arg2 or '').lower() in allowed_functions:return sqlite3.SQLITE_OK
                    return sqlite3.SQLITE_DENY
                connection.set_authorizer(authorize)
                cursor=connection.execute(query['sql'],parameters)
                rows=cursor.fetchmany(limit+1)
                result=normalize(rows,[d[0] for d in cursor.description],limit)
            finally:connection.close()
        else:
            import psycopg
            dsn=os.environ.get(source['dsn_env'])
            if not dsn:raise SourceError('Data source credential is not configured')
            # Database role privileges define accessible tables/functions for PostgreSQL.
            with psycopg.connect(dsn,connect_timeout=timeout,options=f'-c statement_timeout={timeout*1000} -c default_transaction_read_only=on') as connection:
                connection.read_only=True
                with connection.cursor(name="sentinel_evidence") as cursor:
                    cursor.execute(query['sql'],parameters)
                    result=normalize(cursor.fetchmany(limit+1),[d.name for d in cursor.description],limit)
        result['source_id']=source['id']
        result['query_id']=query['name']
        return result
    except SourceError:raise
    except ImportError:raise SourceError('Install the PostgreSQL optional dependency for this data source') from None
    except Exception:raise SourceError('Evidence query failed; check approved SQL, source permissions and limits') from None


def register_sources(registry):
    from .tools import Tool,schema
    # Synthetic emails never trigger reads from a real organization's databases.
    sources=load_sources(registry.c)
    import hashlib
    registry.sources_sha256=hashlib.sha256(json.dumps(sources,sort_keys=True).encode()).hexdigest()
    for source in sources:
        for query in source['queries']:
            def run(_source=source,_query=query,**arguments):
                if registry.message.get('source')=='demo':raise SourceError('Real data sources are disabled for sample messages')
                inverse=registry.privacy.original_values
                def resolve(value):
                    if not isinstance(value,str):return value
                    return re.sub(r"\[[A-Z]+_\d+\]",lambda match:inverse.get(match[0],match[0]),value)
                return execute_query(_source,_query,{k:resolve(v) for k,v in arguments.items()})
            registry.add(Tool(query['name'],query['description']+('\nApproved schema context: '+source['schema_notes'] if source.get('schema_notes') else ''),schema(query.get('parameters',{}),query.get('required',[])),run,
                title=query.get('title',{}),default_mode=query.get('mode','auto'),applicability=query.get('when','Use when relevant to the investigation.'),
                available=lambda output,q=query:bool(output.get('available')) and (bool(output.get('rows')) if q.get('require_rows',True) else True),preview=False,real_data=True))
