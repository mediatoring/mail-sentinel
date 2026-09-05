"""Bounded MIME parsing and read-only, UID-based IMAP ingestion."""
import hashlib
import imaplib
import json
import os
import re
import ssl
from contextlib import contextmanager
from email import policy
from email.parser import BytesParser
from email.utils import parseaddr
from html.parser import HTMLParser


class TextHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text, self.links = [], []

    def handle_data(self, data):
        self.text.append(data)

    def handle_starttag(self, tag, attrs):
        for k, v in attrs:
            if tag == "a" and k == "href" and v:
                self.links.append(v)


def parse_email(raw, max_bytes=1_000_000):
    if len(raw) > max_bytes:
        raise ValueError("Message exceeds configured size limit")
    m = BytesParser(policy=policy.default).parsebytes(raw)
    plain, html, attachments = [], [], []
    for n, part in enumerate(m.walk()):
        if n > 150:
            raise ValueError("Too many MIME parts")
        if part.is_multipart():
            continue
        data = part.get_payload(decode=True) or b""
        if part.get_content_disposition() == "attachment" or part.get_filename():
            attachments.append({"filename": str(part.get_filename() or "unnamed"), "mime": part.get_content_type(), "size": len(data), "sha256": hashlib.sha256(data).hexdigest()})
        elif part.get_content_type() in {"text/plain", "text/html"}:
            charset = part.get_content_charset() or "utf-8"
            try:
                text = data.decode(charset, errors="replace")
            except LookupError:
                text = data.decode("utf-8", errors="replace")
            (plain if part.get_content_type() == "text/plain" else html).append(text)
    h = TextHTML()
    h.feed("\n".join(html))
    body = "\n".join(plain) if plain else " ".join(h.text)
    urls = list(dict.fromkeys(h.links + re.findall(r"https?://[^\s<>\"']+", body)))[:50]
    return {"id": hashlib.sha256(raw).hexdigest(), "subject": str(m.get("Subject", "")),
            "sender": str(m.get("From", "")), "sender_address": parseaddr(str(m.get("From", "")))[1],
            "reply_to": parseaddr(str(m.get("Reply-To", "")))[1], "body": body[:50000],
            "body_truncated": len(body) > 50000, "urls": [u.rstrip(".,;)") for u in urls],
            "attachments": attachments, "authentication_note": "Authentication headers are not verified by this parser. Consult your trusted receiving mail server.",
            "source": "file"}


class Mailbox:
    def __init__(self, config):
        self.c = config

    @contextmanager
    def connect(self, readonly=True):
        if not self.c.imap_host or not self.c.imap_user:
            raise ValueError("Configure IMAP host, user and password environment variable")
        client = imaplib.IMAP4_SSL(self.c.imap_host, self.c.imap_port, ssl_context=ssl.create_default_context(), timeout=self.c.timeout)
        try:
            if self.c.imap_auth == "oauth2":
                token = os.environ.get(self.c.imap_token_env, "")
                if not token or any(ch in token+self.c.imap_user for ch in "\x01\r\n"):
                    raise ValueError("Configure a valid IMAP OAuth access token")
                auth = ("user="+self.c.imap_user+"\x01auth=Bearer "+token+"\x01\x01").encode()
                client.authenticate("XOAUTH2", lambda challenge: auth if not challenge else b"")
            else:
                client.login(self.c.imap_user, os.environ[self.c.imap_password_env])
            typ, _ = client.select('"' + self.c.imap_folder + '"', readonly=readonly)
            if typ != "OK":
                raise ValueError("Configured IMAP folder does not exist")
            yield client
        finally:
            try:
                client.logout()
            except Exception:
                pass

    def identity(self, client):
        response = client.response("UIDVALIDITY")[1]
        if not response or not response[0]:
            raise ValueError("Server did not provide UIDVALIDITY")
        return response[0].decode("ascii")

    def fetch(self):
        messages = []
        with self.connect() as client:
            validity = self.identity(client)
            response=client.response("UIDNEXT")[1]
            if not response or not response[0] or not response[0].isdigit():
                raise ValueError("Server did not provide UIDNEXT")
            high=int(response[0])-1
            uids=[]
            # Bound both search responses and work per interactive load.
            for _ in range(20):
                if high<1 or len(uids)>=self.c.max_messages: break
                low=max(1,high-499)
                typ,rows=client.uid("search",None,"UID",f"{low}:{high}")
                if typ!="OK": raise ValueError("IMAP search failed")
                page=(rows[0] or b"").split()
                if len(page)>500 or any(not uid.isdigit() or not low<=int(uid)<=high for uid in page):
                    raise ValueError("Invalid UID search response")
                uids=page+uids
                high=low-1
            for uid in uids[-self.c.max_messages:]:
                typ, size_rows = client.uid("fetch", uid, "(RFC822.SIZE)")
                match = re.search(rb"RFC822.SIZE (\d+)", b" ".join(x for x in size_rows if isinstance(x, bytes))) if typ == "OK" else None
                if not match or int(match[1]) > self.c.max_message_bytes:
                    continue
                typ, fetched = client.uid("fetch", uid, "(BODY.PEEK[])")
                if typ != "OK":
                    continue
                for row in fetched:
                    if isinstance(row, tuple):
                        msg = parse_email(row[1], self.c.max_message_bytes)
                        ref = {"host": self.c.imap_host, "port":self.c.imap_port, "user": self.c.imap_user, "folder": self.c.imap_folder, "uidvalidity": validity, "uid": uid.decode("ascii")}
                        msg.update(source="imap", imap_ref=ref)
                        msg["id"] = hashlib.sha256(json.dumps(ref,sort_keys=True).encode()).hexdigest()
                        messages.append(msg)
        return messages

    def quarantine(self, ref):
        if not self.c.allow_quarantine:
            raise PermissionError("Quarantine disabled by administrator")
        if any(ref.get(k) != v for k, v in {"host": self.c.imap_host, "port": self.c.imap_port, "user": self.c.imap_user, "folder": self.c.imap_folder}.items()) or not str(ref.get("uid", "")).isdigit():
            raise ValueError("Mailbox identity mismatch")
        with self.connect(readonly=False) as client:
            if self.identity(client) != ref["uidvalidity"]:
                raise ValueError("Mailbox UIDVALIDITY changed; reload message")
            if b"MOVE" not in client.capabilities:
                raise ValueError("Server must support UID MOVE; no destructive fallback")
            typ, _ = client.uid("MOVE", ref["uid"], '"' + self.c.quarantine_folder + '"')
            if typ != "OK":
                raise ValueError("UID MOVE failed; verify destination folder exists")


    def discover(self, store):
        """Checkpoint one bounded UID window. Repeated calls cover the entire mailbox."""
        import json
        from datetime import date
        with self.connect() as client:
            validity = self.identity(client)
            response = client.response("UIDNEXT")[1]
            if not response or not response[0] or not response[0].isdigit():
                raise ValueError("Server did not provide UIDNEXT")
            highest = int(response[0])-1
            identity = {"host": self.c.imap_host, "port": self.c.imap_port, "user": self.c.imap_user, "folder": self.c.imap_folder, "uidvalidity": validity}
            scope = json.dumps({**identity,"since":self.c.queue_since},sort_keys=True)
            low = store.checkpoint(scope)+1
            if low > highest:
                return False
            high = min(highest,low+499)
            criteria = ["UID",str(low)+":"+str(high)]
            if self.c.queue_since:
                d=date.fromisoformat(self.c.queue_since)
                month=["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][d.month-1]
                criteria += ["SINCE",f"{d.day:02}-{month}-{d.year}"]
            typ, rows = client.uid("search", None, *criteria)
            if typ != "OK":
                raise ValueError("IMAP discovery failed")
            uids = (rows[0] or b"").split()
            if len(uids)>500 or any(not u.isdigit() or not low<=int(u)<=high for u in uids):
                raise ValueError("Invalid UID search response")
            store.enqueue_page(scope,[{**identity,"uid":u.decode("ascii")} for u in uids],high)
            return high < highest

    def fetch_ref(self, ref):
        if any(ref.get(k)!=v for k,v in {"host":self.c.imap_host,"port":self.c.imap_port,"user":self.c.imap_user,"folder":self.c.imap_folder}.items()):
            raise LookupError("Mailbox changed")
        uid=str(ref.get("uid",""))
        if not uid.isdigit():
            raise LookupError("Invalid UID")
        with self.connect() as client:
            if self.identity(client)!=ref["uidvalidity"]:
                raise LookupError("UIDVALIDITY changed")
            typ, sizes=client.uid("fetch",uid,"(RFC822.SIZE)")
            match=re.search(rb"RFC822.SIZE (\d+)",b" ".join(x for x in sizes if isinstance(x,bytes))) if typ=="OK" else None
            if not match or int(match[1])>self.c.max_message_bytes:
                raise LookupError("Message missing or exceeds size limit")
            typ,rows=client.uid("fetch",uid,"(BODY.PEEK[])")
            if typ!="OK":
                raise LookupError("Message unavailable")
            for row in rows:
                if isinstance(row,tuple):
                    message=parse_email(row[1],self.c.max_message_bytes)
                    message.update(source="imap",imap_ref=ref,id=hashlib.sha256(json.dumps(ref,sort_keys=True).encode()).hexdigest())
                    return message
            raise LookupError("Message disappeared")
