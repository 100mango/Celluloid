import json,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
import optional_export_budget as gate

class OptionalBudgetTests(unittest.TestCase):
    def test_aggregate_window_limits_each_export_and_leaves_cleanup_time(self):
        clock=[100.0]
        def run(args,timeout,**kwargs):clock[0]+=timeout;return subprocess.CompletedProcess(args,0,'summary','')
        with patch.object(gate.time,'monotonic',side_effect=lambda:clock[0]),patch.object(gate,'run_process',side_effect=run) as process:
            budget=gate.OptionalExportBudget()
            self.assertEqual(budget.run(['export','first'],60).stdout,b'summary')
            budget.run(['export','second'],60);budget.run(['export','third'],60)
            self.assertEqual([c.kwargs['timeout'] for c in process.call_args_list],[60,60,45])
            with self.assertRaises(gate.OptionalExportError):budget.run(['export','fourth'],60)
            self.assertEqual(process.call_count,3);self.assertLessEqual(clock[0],280);self.assertEqual(budget.report()['aggregate_limit_seconds'],180)
    def test_job_tail_can_shorten_optional_budget_and_never_expands_it(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(gate.time,'monotonic',return_value=2400.0),patch.object(gate,'run_process',return_value=subprocess.CompletedProcess([],0,'','')) as process:
            path=Path(folder)/'clock.json';path.write_text(json.dumps({'source_sha':'a'*40,'started_monotonic':100.0,'started_unix':10000.0,'execution_budget_seconds':2460}))
            budget=gate.OptionalExportBudget(path,'a'*40);budget.run(['export','last'],60)
            self.assertEqual(process.call_args.kwargs['timeout'],25);self.assertEqual(budget.deadline,2440)
    def test_expired_or_invalid_clock_stops_optional_processes(self):
        for clock in [{'source_sha':'wrong','started_monotonic':100.0,'started_unix':10000,'execution_budget_seconds':2460}, {'source_sha':'a'*40,'started_monotonic':False,'started_unix':10000,'execution_budget_seconds':2460}, {'source_sha':'a'*40,'started_monotonic':100.0,'started_unix':10000,'execution_budget_seconds':2460}]:
            with tempfile.TemporaryDirectory() as folder,patch.object(gate.time,'monotonic',return_value=2500.0),patch.object(gate,'run_process') as process:
                path=Path(folder)/'clock.json';path.write_text(json.dumps(clock));budget=gate.OptionalExportBudget(path,'a'*40)
                with self.assertRaises(gate.OptionalExportError):budget.run(['export','last'],60)
                process.assert_not_called()
    def test_timeout_keeps_cleanup_unconfirmed_and_does_not_claim_acceptance(self):
        with patch.object(gate.time,'monotonic',return_value=100.0),patch.object(gate,'run_process',side_effect=TimeoutError('owned process cleanup uncertain')):
            budget=gate.OptionalExportBudget()
            with self.assertRaises(gate.OptionalExportError):budget.run(['export','last'],60)
            self.assertEqual(budget.report()['events'][0]['state'],'export failed; cleanup unconfirmed')
            with self.assertRaisesRegex(gate.OptionalExportError,'later exporters withheld'):budget.run(['export','next'],60)
            self.assertEqual(len(budget.report()['events']),1)
    def test_collector_prioritizes_complete_mandatory_packets_before_optional_budget(self):
        root=Path(__file__).resolve().parents[1];source=(root/'Scripts/collect_native_evidence.py').read_text()
        position=source.index('optional_budget=OptionalExportBudget')
        for marker in ['record=verify_collected','collect_text_observations']:
            self.assertLess(source.index(marker),position)
        self.assertLess(source.index("layer_from_log(TEMP/'mac.log'"),position)
        self.assertIn("manifest['optional_export_budget']=optional_budget.report()",source)
        self.assertIn('cleanup not assumed',source)

if __name__=='__main__':unittest.main()
