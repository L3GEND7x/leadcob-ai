from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.api.routes_crm import _pipeline_stage_counts
from app.db.database import Base
from app.db.models import Company


def test_pipeline_stage_counts_group_by_column_and_merge_default():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    statements = []

    def record(_conn, _cursor, statement, _params, _context, _many):
        statements.append(statement)

    event.listen(engine, 'before_cursor_execute', record)
    try:
        with Session(engine) as db:
            db.add_all([Company(name='Sem etapa'), Company(name='Etapa padrão', pipeline_stage='identificada'),
                        Company(name='Qualificada', pipeline_stage='qualificada')])
            db.commit()
            assert _pipeline_stage_counts(db) == {'identificada': 2, 'qualificada': 1}
    finally:
        event.remove(engine, 'before_cursor_execute', record)
        engine.dispose()

    group_queries = [sql for sql in statements if 'FROM companies GROUP BY' in sql]
    assert len(group_queries) == 1
    assert 'GROUP BY companies.pipeline_stage' in group_queries[0]
    assert 'coalesce' not in group_queries[0].lower()
