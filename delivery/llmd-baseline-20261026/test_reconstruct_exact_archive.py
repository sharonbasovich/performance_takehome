"""Tiny offline system tests; no real archive, public blobs or network touched."""
from contextlib import ExitStack,redirect_stdout
import hashlib,io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import reconstruct_exact_archive as r

def sha(raw):return hashlib.sha256(raw).hexdigest()
class ReconstructionTests(unittest.TestCase):
 def fixture(self,root):
  meta=root/'metadata';blobs=root/'blobs';meta.mkdir();blobs.mkdir();(meta/'segments').mkdir()
  prefix=b'ORIGINAL_HEADER\0';suffix=b'\0EXACT_PADDING_AND_SUFFIX'
  (meta/'segments/000.bin').write_bytes(prefix);(meta/'segments/024.bin').write_bytes(suffix)
  segments=[{'kind':'exact_export_bytes','offset':0,'bytes':len(prefix),'sha256':sha(prefix),'file':'segments/000.bin'}]
  assembled=prefix
  for index in range(23):
   payload=f'compressed-payload-{index:02d}'.encode();digest=sha(payload);(blobs/digest).write_bytes(payload)
   segments.append({'kind':'public_base_compressed_blob','offset':len(assembled),'bytes':len(payload),'sha256':digest})
   assembled+=payload
  segments.append({'kind':'exact_export_bytes','offset':len(assembled),'bytes':len(suffix),'sha256':sha(suffix),'file':'segments/024.bin'})
  assembled+=suffix;receipt=b'{"status":"tiny fixture only"}\n';(meta/'original-receipt.json').write_bytes(receipt)
  manifest={'archive_bytes':len(assembled),'archive_sha256_from_pinned_original_receipt':sha(assembled),'original_receipt_sha256':sha(receipt),'layer_count':23,'segments':segments}
  raw=json.dumps(manifest).encode();(meta/'reconstruction-manifest.json').write_bytes(raw)
  constants={'MANIFEST_SHA':sha(raw),'ARCHIVE_SHA':sha(assembled),'ARCHIVE_BYTES':len(assembled),'RECEIPT_SHA':sha(receipt)}
  return meta,blobs,assembled,constants
 def run_case(self,meta,blobs,out,constants):
  with ExitStack() as stack:
   for key,value in constants.items():stack.enter_context(patch.object(r,key,value))
   stack.enter_context(redirect_stdout(io.StringIO()))
   return r.main(['--execute-reviewed','--metadata-dir',str(meta),'--blob-dir',str(blobs),'--output',str(out),'--manifest-sha256',constants['MANIFEST_SHA']])
 def test_exact_reconstruction_and_exclusive_output(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp).resolve();meta,blobs,expected,pins=self.fixture(root);out=root/'exact.tar'
   self.assertEqual(self.run_case(meta,blobs,out,pins),0);self.assertEqual(out.read_bytes(),expected)
   with self.assertRaises(ValueError):self.run_case(meta,blobs,out,pins)
   self.assertEqual(out.read_bytes(),expected)
 def test_bad_blob_rejects_before_output(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp).resolve();meta,blobs,expected,pins=self.fixture(root);next(blobs.iterdir()).write_bytes(b'bad')
   with self.assertRaises(ValueError):self.run_case(meta,blobs,root/'bad.tar',pins)
   self.assertFalse((root/'bad.tar').exists());self.assertFalse((root/'bad.tar.reconstruct.partial').exists())
 def test_coverage_corruption_rejected(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp).resolve();meta,blobs,expected,pins=self.fixture(root)
   manifest=json.loads((meta/'reconstruction-manifest.json').read_bytes());manifest['segments'][1]['offset']+=1
   with ExitStack() as stack:
    for key,value in pins.items():stack.enter_context(patch.object(r,key,value))
    with self.assertRaisesRegex(ValueError,'coverage'):r.validate_manifest(manifest)
 def test_default_no_reads_or_writes(self):
  with patch.object(Path,'open',side_effect=AssertionError('unexpected file access')),redirect_stdout(io.StringIO()):self.assertEqual(r.main([]),0)
if __name__=='__main__':unittest.main()
