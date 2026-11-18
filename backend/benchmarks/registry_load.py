"""Synthetic registry benchmark. Never use application DATABASE_URL or production."""
import argparse
import json
import os
import resource
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import create_engine, insert
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from app.db.database import Base
from app.db.models import Company, BusinessContact
from app.services.cnpj import _dv, WEIGHTS_1, WEIGHTS_2
from app.services.registry_coverage import registry_coverage
from app.services.lead_qualification import qualification
from app.services.contact_targets import targets


def run(url, records=53000, repeats=5, workers=4):
    parsed=make_url(url)
    if parsed.get_backend_name()!="postgresql" or parsed.host not in ("127.0.0.1","localhost") or parsed.database!="leadcob_test":
        raise ValueError("Only dedicated local PostgreSQL leadcob_test is allowed.")
    if not 100<=records<=100000 or not 2<=repeats<=10 or not 1<=workers<=4:
        raise ValueError("Invalid workload bounds.")
    schema="bench_"+uuid4().hex
    admin=create_engine(url)
    engine=None
    created=False
    try:
        with admin.begin() as conn:
            conn.exec_driver_sql("CREATE SCHEMA "+schema)
        created=True
        engine=create_engine(url,connect_args={"options":"-csearch_path="+schema},
                             pool_size=workers,max_overflow=0)
        Base.metadata.create_all(engine)
        now=datetime.now(timezone.utc)
        with engine.begin() as conn:
            for start in range(1,records+1,1000):
                batch=[]
                for i in range(start,min(start+1000,records+1)):
                    base=f"{i:012d}"
                    first=_dv(base,WEIGHTS_1)
                    key=base+first+_dv(base+first,WEIGHTS_2)
                    batch.append(dict(id=i,name=f"Synthetic {i}",cnpj=key,state="AM",city="Manaus",
                        registration_status="ATIVA",registry_source="Synthetic benchmark",
                        registry_updated_at=now,cnae_main="4631100",website="https://example.test"))
                conn.execute(insert(Company),batch)
            for start in range(1,records+1,1000):
                batch=[dict(company_id=i,kind="email",value="financeiro@example.test",
                    source_name="Synthetic benchmark",status="verificado",department="geral")
                    for i in range(start,min(start+1000,records+1)) if i%4==0]
                if batch:
                    conn.execute(insert(BusinessContact),batch)
            conn.exec_driver_sql("ANALYZE")
        functions={
            "inventory":lambda db:registry_coverage(db,"AM","Manaus"),
            "qualification":lambda db:qualification(db,"AM","Manaus",limit=50),
            "missing_email":lambda db:targets(db,"AM","Manaus","email",limit=50),
        }
        def measure(name):
            start=time.perf_counter()
            with Session(engine) as db:
                value=functions[name](db)
            elapsed=time.perf_counter()-start
            if name=="inventory":
                assert value["unique_valid_cnpjs"]==records
            elif name=="qualification":
                assert value["unique_cnpjs"]==records
                assert value["contact_coverage"]["with_verified_channel"]==records//4
                assert len(value["items"])==50
            else:
                assert value["active_unique_cnpjs"]==records
                assert value["missing_channel"]==records-records//4
                assert len(value["items"])==50
            return elapsed
        report={}
        for name in functions:
            measure(name) # warmup
            samples=[measure(name) for _ in range(repeats)]
            with ThreadPoolExecutor(max_workers=workers) as pool:
                start=time.perf_counter()
                parallel=list(pool.map(measure,[name]*workers))
                wall=time.perf_counter()-start
            report[name]={"sequential_seconds":samples,"median_seconds":statistics.median(samples),
                          "max_seconds":max(samples),"concurrent_seconds":parallel,
                          "concurrent_wall_seconds":wall}
        return {"synthetic":True,"records":records,"contacts":records//4,"workers":workers,
                "repeats":repeats,"peak_process_rss_kib_linux":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                "process_cpu_seconds":time.process_time(),"results":report,
                "note":"Service-level measurements, not HTTP latency or production capacity."}
    finally:
        if engine is not None:
            engine.dispose()
        if created:
            with admin.begin() as conn:
                conn.exec_driver_sql("DROP SCHEMA "+schema+" CASCADE")
        admin.dispose()


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--records",type=int,default=53000)
    parser.add_argument("--repeats",type=int,default=5)
    parser.add_argument("--workers",type=int,default=4)
    args=parser.parse_args()
    print(json.dumps(run(os.environ["LEADCOB_TEST_POSTGRES_URL"],args.records,args.repeats,args.workers),indent=2))
