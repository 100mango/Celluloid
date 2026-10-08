import json,subprocess,unittest
from unittest.mock import Mock
from file_open_observation import capture,MESSAGE
class FileOpenObservationTests(unittest.TestCase):
    def invoke(self,rows,status=0):
        run=Mock(return_value=subprocess.CompletedProcess([],status,json.dumps(rows),'stderr deliberately not uploaded'))
        report=capture(run,'owned-udid','a'*40,'b'*64);return report,run
    def test_exact_process_message_metadata_remains_unclassified(self):
        report,run=self.invoke([{'processImagePath':'/Sim/Celluloid.app/Celluloid','eventMessage':MESSAGE,'senderImagePath':'/System/Library/Example.framework/Example','unrequested':'must not retain'}])
        self.assertTrue(report['observed_records_available']);self.assertFalse(report['classified']);self.assertFalse(report['acceptance']);self.assertNotIn('unrequested',report['records'][0])
        args=run.call_args;self.assertEqual(args.kwargs['timeout'],20);self.assertEqual(args.args[0][2:4],['spawn','owned-udid']);self.assertIn('process == "Celluloid" AND eventMessage == "'+MESSAGE+'"',args.args[0])
    def test_unknown_empty_oversized_or_failed_queries_are_unavailable(self):
        for rows,status in [([],0),([{'processImagePath':'/wrong','eventMessage':MESSAGE}],0),([{'processImagePath':'/Sim/Celluloid.app/Celluloid','eventMessage':'other'}],0),([],1),([{}]*13,0)]:
            report,_=self.invoke(rows,status);self.assertFalse(report['observed_records_available']);self.assertFalse(report['classified']);self.assertFalse(report['acceptance'])
        report=capture(Mock(side_effect=TimeoutError('bounded query')),'owned','a'*40,'b'*64);self.assertFalse(report['observed_records_available']);self.assertIn('TimeoutError',report['unavailable_reason'])
if __name__=='__main__':unittest.main()
