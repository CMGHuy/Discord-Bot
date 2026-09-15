"""PostgreSQL persistence layer.

Nothing outside this package imports SQLAlchemy directly.  Repositories will
return plain dictionaries so the existing JSON-store call sites keep their
flat-record contract during the staged migration.
"""
