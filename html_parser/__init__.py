"""Auditable HTML paragraph/table extraction, without LLM rewriting."""
from html.parser import HTMLParser
from pathlib import Path
import hashlib,json,re
from pdf_parser.retrieval_units import build_units

class Blocks(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True);self.ignored=0;self.table=0;self.active=None;self.buffer=[];self.rows=[];self.section=''
    def flush(self):
        text=re.sub(r'[ \t\r\f\v]+',' ',''.join(self.buffer)).strip()
        if text:
            if self.active and self.active.startswith('h'): self.section=text
            else:self.rows.append(dict(text=text,block_type='table_text' if self.active=='table' else 'list' if self.active=='li' else 'paragraph',section=self.section))
        self.buffer=[]
    def handle_starttag(self,tag,attrs):
        if tag in {'script','style','nav','header','footer','noscript'}: self.ignored+=1;return
        if self.ignored:return
        if tag=='table':
            if not self.table:self.flush();self.active='table'
            self.table+=1;return
        if self.table:
            if tag in {'tr','td','th'}:self.buffer.append('\n' if tag=='tr' else ' | ')
            return
        if tag in {'p','li','h1','h2','h3','h4','div','section','article'}:
            self.flush();self.active=tag
        elif tag=='br':self.buffer.append('\n')
    def handle_endtag(self,tag):
        if tag in {'script','style','nav','header','footer','noscript'}:
            self.ignored=max(0,self.ignored-1);return
        if self.ignored:return
        if tag=='table':
            self.table=max(0,self.table-1)
            if not self.table:self.flush();self.active=None
            return
        if self.table:return
        if tag in {'p','li','h1','h2','h3','h4','div','section','article'}:self.flush();self.active=None
    def handle_data(self,data):
        if not self.ignored:self.buffer.append(data)

def parse_html(path, output):
    path=Path(path);output=Path(output);output.mkdir(parents=True,exist_ok=True)
    raw=path.read_bytes();digest=hashlib.sha256(raw).hexdigest();parser=Blocks();parser.feed(raw.decode('utf-8',errors='replace'));parser.flush()
    chunks=[]
    for i,row in enumerate(parser.rows):
        cid='H_'+hashlib.sha256(f'{digest}:html-v1:{i}:{row["text"]}'.encode()).hexdigest()[:24]
        chunks.append(dict(row,chunk_id=cid,source_id=digest,pages=[],location=dict(element_order=i+1,section=row['section']),bboxes=[],quote_match=None,quality_flags=['html_structure_requires_review'],retrieval_text='[Section]\n'+row['section']+'\n[Content]\n'+row['text']))
    for i,c in enumerate(chunks):
        c.update(prev_chunk_id=chunks[i-1]['chunk_id'] if i else None,next_chunk_id=chunks[i+1]['chunk_id'] if i+1<len(chunks) else None)
    def write(name,rows):(output/name).write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in rows))
    write('retrieval_chunks.jsonl',chunks);write('retrieval_units.jsonl',build_units(chunks))
    (output/'parse_manifest.json').write_text(json.dumps(dict(source_file_sha256=digest,source_file=str(path),parser='local-html-v1',chunks=len(chunks),search_complete=False,quote_match=None),ensure_ascii=False,indent=2))
    return len(chunks)
