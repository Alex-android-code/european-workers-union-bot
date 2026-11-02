"""Process lock for a single bot on a shared data volume (Unix/Windows)."""
from contextlib import contextmanager
import os

@contextmanager
def acquire(path):
 with open(path,'a+b') as stream:
  if os.name=='nt':
   import msvcrt
   stream.seek(0);stream.write(b'0');stream.flush();stream.seek(0)
   msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
  else:
   import fcntl
   fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
  try:yield
  finally:
   if os.name=='nt':
    stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
   else:fcntl.flock(stream.fileno(),fcntl.LOCK_UN)
