"""Compact runtime keeps source totals while avoiding the full event/master load."""
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from analysis.build_runtime_snapshot import build
from backend.app.capabilities.data import service, composition

class CompactRuntimeTests(unittest.TestCase):
    def test_source_totals_and_selected_evidence_survive_compaction(self):
        source = json.loads(service.MOCK_SNAPSHOT_FILE.read_text())
        sid=source['manifest']['snapshot_id']
        with TemporaryDirectory() as temp:
            folder=Path(temp);full=folder/f'{sid}.json';full.write_text(json.dumps(source))
            with patch.object(service,'MOCK_SNAPSHOT_FILE',full):
                service.load_snapshot.cache_clear()
                before=composition.snapshot_stats(sid).model_dump()
                build(sid,folder)
                service.load_snapshot.cache_clear()
                small=service.load_snapshot(sid)
                self.assertEqual(small['manifest'].model_dump(),source['manifest'])
                self.assertEqual(len(small['profiles']),len(source['profiles']))
                self.assertEqual(len(small['history']),len(source['history']))
                self.assertEqual(small['events'],[])
                self.assertEqual(small['instruments'],[])
                self.assertEqual(sum(small['requirement_summary']['by_kind'].values()),len(source['requirements']))
                self.assertEqual(composition.snapshot_stats(sid).model_dump(),before)
                full_evidence=service.get_customer_detail(sid,'SYN-001',full_evidence=True)
                self.assertEqual({r.id for r in full_evidence['requirements']},{r['id'] for r in source['requirements'] if r['customer_id']=='SYN-001'})
        service.load_snapshot.cache_clear()

    def test_concurrent_cold_reads_parse_once(self):
        service.load_snapshot.cache_clear()
        with patch.object(service,'_snapshot_path',wraps=service._snapshot_path) as lookup:
            with ThreadPoolExecutor(max_workers=5) as pool:
                outputs=list(pool.map(service.load_snapshot,['synthetic-v1']*5))
            self.assertEqual(lookup.call_count,1)
            self.assertTrue(all(s is outputs[0] for s in outputs))
        service.load_snapshot.cache_clear()

    def test_browser_window_query_is_accepted(self):
        import os
        from fastapi.testclient import TestClient
        from backend.app.main import app
        with TemporaryDirectory() as temp, patch.dict(os.environ, {"PECAL_DEMO_DB":str(Path(temp)/"workflow.db"), "PECAL_ANALYTICS_ROOT":str(Path(temp)/"analytics"), "PECAL_OPPORTUNITY_ROOT":str(Path(temp)/"opportunities")}):
            service.load_snapshot.cache_clear()
            with TestClient(app) as client:
                good=client.get("/api/v2/opportunities",params={"snapshot_id":"synthetic-v1","window_days":"90"})
                self.assertEqual(good.status_code,200,good.text)
                bad=client.get("/api/v2/opportunities",params={"snapshot_id":"synthetic-v1","window_days":"45"})
                self.assertEqual(bad.status_code,422)
            service.load_snapshot.cache_clear()
