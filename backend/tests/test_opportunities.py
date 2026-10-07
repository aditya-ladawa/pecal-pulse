import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.contracts.sales_v2 import Requirement
from backend.app.capabilities.analytics.opportunities import due_requirements, fit_map, coordinates, assign
from backend.app.capabilities.data import service

class OpportunityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = patch.dict(os.environ, {'PECAL_DEMO_DB': str(Path(self.tmp.name)/'workflow.sqlite3'),
            'PECAL_ANALYTICS_ROOT': str(Path(self.tmp.name)/'analytics'), 'PECAL_OPPORTUNITY_ROOT': str(Path(self.tmp.name)/'opportunities')})
        env.start(); self.addCleanup(env.stop)
        service.load_snapshot.cache_clear(); self.addCleanup(service.load_snapshot.cache_clear)
        self.client = TestClient(app); self.addCleanup(self.client.close)

    def get(self, **params):
        res = self.client.get('/api/v2/opportunities', params={'snapshot_id': 'synthetic-v1', **params})
        self.assertEqual(res.status_code, 200, res.text)
        return res.json()

    def test_sample_and_pagination_never_change_totals(self):
        all_rows = self.get(display_limit=0, limit=100, window_days=90)
        sample = self.get(display_limit=1, limit=1)
        self.assertEqual(sample['metrics'], all_rows['metrics'])
        self.assertEqual(sample['selected_count'], all_rows['selected_count'])
        self.assertLessEqual(len(sample['points']), 1)
        self.assertEqual(sample['selected_count'], len(all_rows['items']))
        cid = next(p['cluster_id'] for p in all_rows['items'] if p['cluster_id'])
        selection = self.get(cluster_id=cid)
        self.assertTrue(all(p['cluster_id'] == cid for p in selection['items']))
        self.assertEqual(selection['selected_count'], sum(p['cluster_id'] == cid for p in all_rows['items']))
        self.assertEqual(selection['model_version'], all_rows['model_version'])

    def test_recorded_dominates_inferred_and_stops_suppress(self):
        def req(rid, kind, due, **kwargs):
            return Requirement(id=rid, customer_id='C', instrument_id='I', group_id='G', kind=kind,
                window_start=due, window_end=due, method=kind, eligibility='eligible', **kwargs)
        inferred = req('i', 'nominal_interval', '2026-09-10')
        recorded = req('r', 'recorded', '2027-01-01')
        self.assertEqual(due_requirements([inferred, recorded], '2026-08-31', 90), [])
        near = recorded.model_copy(update={'window_start':'2026-09-10','window_end':'2026-09-10'})
        self.assertEqual(len(due_requirements([inferred,near], '2026-08-31',90)),1)
        rid = 'C:upcoming:G:2026-09-10:2026-09-10'
        self.assertEqual(due_requirements([inferred,near], '2026-08-31',90,suppressed={rid}),[])
        stopped = near.model_copy(update={'stopped':True,'eligibility':'excluded'})
        self.assertEqual(due_requirements([inferred,stopped], '2026-08-31',90),[])

    def test_unknown_forecasts_remain_null_and_financial_inputs_validate(self):
        body = self.get(unit_contribution=15, assumption_source='User scenario')
        self.assertIsNone(body['scenario']['estimated_contribution'])
        self.assertEqual(body['scenario']['excluded_account_count'], body['selected_count'])
        for params in ({'unit_contribution':15}, {'cluster_id':'not-a-cluster'}, {'group':'invalid'}, {'window_days':13}):
            self.assertEqual(self.client.get('/api/v2/opportunities', params={'snapshot_id':'synthetic-v1', **params}).status_code,422)

    def test_owner_persists_and_suppression_refreshes_counts(self):
        before = self.get()
        owner = self.client.patch('/api/v2/customers/SYN-001/workflow', params={'snapshot_id':'synthetic-v1'}, json={'account_owner':'Ada'})
        self.assertEqual(owner.status_code,200,owner.text)
        after = self.get()
        self.assertEqual(next(p for p in after['items'] if p['customer_id']=='SYN-001')['owner'],'Ada')
        self.assertNotEqual(before['selection_revision'],after['selection_revision'])
        patch_res = self.client.patch('/api/v2/customers/SYN-001/workflow', params={'snapshot_id':'synthetic-v1'}, json={'suppression':{'reason_id':'REQ-001','status':'resolved','note':'No longer needed','updated_at':'2026-10-07T00:00:00Z'}})
        self.assertEqual(patch_res.status_code,200,patch_res.text)
        self.assertLess(self.get()['recorded_total'], after['recorded_total'])
        self.assertEqual(self.get()['model_version'], before['model_version'])

    def test_sparse_population_uses_zones_and_unknown_is_unassigned(self):
        rows = [{'due_quantity':2,'activity_gap':None,'discovery_scale':None,'urgency':80}]
        model = fit_map(rows)
        self.assertEqual(model['quality']['method'],'priority_zones')
        self.assertIsNone(assign(None,None,model))
        self.assertEqual(coordinates({'due_quantity':None,'activity_gap':None,'discovery_scale':None,'urgency':None},model['anchors']), (None,None,None))

if __name__ == '__main__': unittest.main()

class OpportunityAgentTests(OpportunityTests):
    def runtime(self):
        from types import SimpleNamespace
        from backend.app.agents.contracts import WorkspaceContext, TurnContext
        return SimpleNamespace(context=TurnContext(WorkspaceContext(snapshot_id='synthetic-v1',page='dashboard')))

    def test_agent_selection_filters_and_totals_use_same_cohort(self):
        from backend.app.capabilities.workspace.tools import set_opportunity_filters, select_opportunity_cluster, get_opportunity_cohort
        runtime = self.runtime()
        set_opportunity_filters.func(runtime,industry='IND-AUTOMOTIVE')
        result = get_opportunity_cohort.func(runtime)
        self.assertEqual(result['selected_count'], 1)
        self.assertEqual(result['filters']['industry'], 'IND-AUTOMOTIVE')
        self.assertEqual([e['type'] for e in runtime.context.events], ['opportunities.filters.set','ui.navigate'])
        cluster = result['items'][0]['cluster_id']
        if cluster:
            select_opportunity_cluster.func(cluster_id=cluster,runtime=runtime)
            self.assertEqual(get_opportunity_cohort.func(runtime)['selected_count'],1)
        count = len(runtime.context.events)
        with self.assertRaises(ValueError): set_opportunity_filters.func(runtime,group='unknown-category')
        self.assertEqual(len(runtime.context.events),count)

    def test_sector_chart_tools_preserve_null_correlation_cells(self):
        from backend.app.capabilities.workspace.tools import create_chart
        from backend.app.api import v2
        sectors = {'history':[{'industry_id':'I','label':'Industry','monthly':[{'month':'2026-08','calibration_events':4}]}],
            'forecasts':[{'industry_id':'I','forecast_month':'2026-09','expected':5}],
            'correlation':{'labels':['A','B'],'values':[[1,None],[None,1]],'window_start':'2024-01','window_end':'2026-08'}}
        with patch.object(v2,'sectors',return_value={'sectors':sectors}):
            for view in ('sector_activity','sector_outlook','sector_correlation'):
                result=create_chart.func(view=view,runtime=self.runtime())
                self.assertEqual(result['event']['type'],'artifact.created')
            heat=create_chart.func(view='sector_correlation',runtime=self.runtime())['event']['payload']
            self.assertEqual(heat['kind'],'heatmap')
            self.assertIsNone(heat['datasets'][0]['values'][1])
