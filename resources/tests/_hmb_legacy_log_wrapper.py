import logging,runpy,sys
from pathlib import Path
from unittest import mock
original=logging.FileHandler.__init__
def text_handler(self,filename,*args,**kwargs):
 path=Path(filename)
 return original(self,str(path.with_suffix(".txt")) if path.suffix.lower()==".log" else filename,*args,**kwargs)
with mock.patch.object(logging.FileHandler,"__init__",text_handler):
 runpy.run_path(sys.argv.pop(1),run_name="__main__")
