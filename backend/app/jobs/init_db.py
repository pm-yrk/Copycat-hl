from pathlib import Path
from app.db import execute_schema_file

if __name__ == '__main__':
    candidates = [
        Path('/app/schema.sql'),
        Path(__file__).resolve().parents[3] / 'supabase' / 'schema.sql',
        Path(__file__).resolve().parents[2] / 'schema.sql',
    ]
    schema = next((p for p in candidates if p.exists()), None)
    if not schema:
        raise SystemExit('Could not find schema.sql')
    execute_schema_file(str(schema))
    print(f'Database schema initialized from {schema}')
