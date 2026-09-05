"""Execute real SQLite queries with arbitrary business schema and denied writes."""
from contextlib import closing
import copy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from sentinel.config import Config
from sentinel.data_sources import validate_sources,execute_query,SourceError
from sentinel.tools import Registry
from sentinel.privacy import Privacy
from test_security import registry


class DataSourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'business.sqlite3'
        with closing(sqlite3.connect(self.path)) as db:
            db.executescript("CREATE TABLE cases(case_code TEXT, authorized INTEGER); INSERT INTO cases VALUES('Case-AbC',1),('other',0); CREATE TABLE payroll(secret TEXT); INSERT INTO payroll VALUES('private');")
        self.query={'name':'verify_case','description':'Look up a case code and check authorization','sql':'SELECT case_code, authorized FROM cases WHERE case_code = :case_code','parameters':{'case_code':{'type':'string'}},'required':['case_code'],'mode':'conditional','when':'The message requests release of case information.'}
        self.source={'id':'case_records','driver':'sqlite','path':str(self.path),'tables':['cases'],'queries':[self.query]}

    def test_arbitrary_business_schema_and_parameter_binding(self):
        validate_sources({'version':1,'sources':[self.source]})
        result=execute_query(self.source,self.query,{'case_code':'Case-AbC'})
        self.assertEqual(result['rows'],[{'case_code':'Case-AbC','authorized':1}])
        injected=execute_query(self.source,self.query,{'case_code':"' OR 1=1 --"})
        self.assertEqual(injected['rows'],[])

    def test_write_denied_even_when_adapter_is_called_directly(self):
        for sql in ["DELETE FROM cases RETURNING case_code", "ATTACH DATABASE ':memory:' AS extra", "PRAGMA writable_schema=ON", "SELECT load_extension('/tmp/evil')"]:
            with self.assertRaises(SourceError):execute_query(self.source,{**self.query,'sql':sql},{'case_code':'Case-AbC'})
        with closing(sqlite3.connect(self.path)) as db:self.assertEqual(db.execute('SELECT count(*) FROM cases').fetchone()[0],2)

    def test_undeclared_table_is_denied(self):
        with self.assertRaises(SourceError):execute_query(self.source,{**self.query,'sql':'SELECT secret FROM payroll'},{})

    def test_result_limit_marks_incomplete_evidence(self):
        result=execute_query({**self.source,'max_rows':1},{**self.query,'sql':'SELECT * FROM cases'},{})
        self.assertEqual(len(result['rows']),1)
        self.assertTrue(result['truncated']);self.assertFalse(result['available'])

    def test_parameter_cannot_change_sql_or_destination(self):
        reg=self.real_registry()
        with self.assertRaises(ValueError):reg.execute('verify_case',{'case_code':'Case-AbC','sql':'SELECT * FROM payroll'})

    def real_registry(self,privacy=None):
        path=Path(self.tmp.name)/'sources.json';path.write_text(json.dumps({'version':1,'sources':[self.source]}))
        msg={'id':'message','source':'file','body':'Check case','sender':'','subject':'case','urls':[],'attachments':[]}
        return Registry(msg,{},privacy or Privacy(),Config(data_sources_file=str(path)))

    def test_pseudonym_parameters_resolve_locally_preserving_case(self):
        privacy=Privacy(['Case-AbC']);token=privacy.text('Case-AbC')
        reg=self.real_registry(privacy)
        result=reg.execute('verify_case',{'case_code':token})
        self.assertEqual(result['rows'][0]['case_code'],token)
        self.assertNotIn('Case-AbC',json.dumps(result))
        self.assertTrue(result['_check']['available'])

    def test_demo_cannot_access_real_database(self):
        path=Path(self.tmp.name)/'sources.json';path.write_text(json.dumps({'version':1,'sources':[self.source]}))
        reg=registry(data_sources_file=str(path))
        self.assertIn('verify_case',reg.catalog)
        self.assertNotIn('verify_case',reg.tools)
        with self.assertRaises(PermissionError):reg.execute('verify_case',{'case_code':'Case-AbC'})

    def test_duplicate_queries_and_unsafe_config_are_rejected(self):
        for query in [{**self.query,'sql':'DELETE FROM cases'}, {**self.query,'sql':'SELECT * FROM cases; DELETE FROM cases'}]:
            with self.assertRaises(SourceError):validate_sources({'version':1,'sources':[{**self.source,'queries':[query]}]})
        with self.assertRaises(SourceError):validate_sources({'version':1,'sources':[self.source,self.source]})

    def test_database_not_created_if_missing(self):
        missing=Path(self.tmp.name)/'missing.sqlite3'
        with self.assertRaises(SourceError):execute_query({**self.source,'path':str(missing)},self.query,{'case_code':'a'})
        self.assertFalse(missing.exists())

    def test_postgresql_uses_bound_parameters_readonly_and_server_cursor(self):
        from unittest.mock import MagicMock,patch
        import os,sys
        driver=MagicMock();connection=driver.connect.return_value.__enter__.return_value
        cursor=connection.cursor.return_value.__enter__.return_value
        cursor.fetchmany.return_value=[('Case-AbC',1)]
        cursor.description=[type('Column',(),{'name':n})() for n in ['case_code','authorized']]
        source={'id':'case_records','driver':'postgresql','dsn_env':'SENTINEL_CASE_DSN','queries':[self.query]}
        query={**self.query,'sql':'SELECT case_code, authorized FROM approved_cases WHERE case_code = %(case_code)s'}
        with patch.dict(sys.modules,{'psycopg':driver}),patch.dict(os.environ,{'SENTINEL_CASE_DSN':'test-dsn'}):
            result=execute_query(source,query,{'case_code':'Case-AbC'})
        self.assertTrue(connection.read_only)
        self.assertEqual(connection.cursor.call_args.kwargs,{'name':'sentinel_evidence'})
        self.assertIn('default_transaction_read_only=on',driver.connect.call_args.kwargs['options'])
        self.assertEqual(cursor.execute.call_args.args,(query['sql'],{'case_code':'Case-AbC'}))
        self.assertEqual(result['rows'][0]['authorized'],1)
