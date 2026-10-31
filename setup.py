"""Unpack the database (data/construct_laplace.sqlite.xz -> data/construct_laplace.sqlite). Python 3.8 or later, no packages needed."""
import lzma, os, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
src = os.path.join(HERE, 'data', 'construct_laplace.sqlite.xz')
dst = src[:-3]
if os.path.exists(dst):
    print('already unpacked:', os.path.relpath(dst))
else:
    with lzma.open(src) as fi, open(dst, 'wb') as fo:
        shutil.copyfileobj(fi, fo)
    print('unpacked:', os.path.relpath(dst), os.path.getsize(dst) // 2 ** 20, 'MB')
