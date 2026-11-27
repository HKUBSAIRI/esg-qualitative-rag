import sys,json,tempfile,unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from build_index import build
class Fake:
    model='test'; calls=[]
    def encode(self,texts):
        v=np.zeros((len(texts),1024),dtype=np.float32);v[:,0]=1;return v
class IndexTest(unittest.TestCase):
    def test_partition_provenance_and_pending_exclusion(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=Path(tmp)/'registry';r.mkdir();sources=[]
            for code,level in [('001',1),('001',2),('002',1),('003',None)]:
                sid=f'{code}_{level}';s=dict(source_id=sid,company_id=code,source_level=level,metadata_status='registered' if level else 'pending_review');sources.append(s)
                if level:
                    d=r/'linked'/sid;d.mkdir(parents=True)
                    c=dict(chunk_id='p',text='工资支付',source_id=sid,company_id=code)
                    u=dict(unit_id='u',parent_chunk_id='p',text='工资支付',retrieval_text='工资支付',char_start=0,char_end=4,source_id=sid,company_id=code)
                    for f,row in [('retrieval_chunks.jsonl',c),('retrieval_units.jsonl',u)]: (d/f).write_text(json.dumps(row)+'\n')
            (r/'sources.jsonl').write_text(''.join(json.dumps(s)+'\n' for s in sources))
            out=Path(tmp)/'index';summary=build(r,out,Fake())
            self.assertEqual(summary['indexes'],3);self.assertEqual(len(summary['skipped']),1)
            self.assertEqual(np.load(out/'001/L1/embeddings.npy').shape,(1,1024))
            self.assertFalse((out/'003').exists())
if __name__=='__main__':unittest.main()
