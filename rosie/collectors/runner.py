import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from . import ec2, rds, lambda_, ecs, s3, iam, ssm

logger = logging.getLogger(__name__)

COLLECTORS = [ec2, rds, lambda_, ecs, s3, iam, ssm]

def run_all(region: str, account_id: str) -> list[dict]:
    all_resources = []
    def run_collector(collector):
        try:
            return collector.collect(region, account_id)
        except Exception as e:
            logger.warning(f"Collector {collector.__name__} failed: {e}")
            return []
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(run_collector, c): c for c in COLLECTORS}
        for future in as_completed(futures):
            result = future.result()
            all_resources.extend(result)
    return all_resources
