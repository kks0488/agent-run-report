import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree as ET

from agent_run_report import __version__
from agent_run_report.cli import main
from agent_run_report.metrics import redact_home, summarize
from agent_run_report.parsers import Session, UTC, discover, load_sessions, parse_claude, parse_codex, timestamp
from agent_run_report.render import bar_chart, daily_chart, nice_ticks, render_html, tick_label

DEMO = Path(__file__).resolve().parents[1] / 'agent_run_report' / 'demo'
START = datetime(2026, 10, 6, 9, tzinfo=UTC)


class TemporaryLogs(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, rows, name='session.jsonl'):
        path = self.root / name
        path.write_text('\n'.join(json.dumps(row) for row in rows) + '\n', encoding='utf-8')
        return path

    def claude(self, kind, minute=0, **values):
        return dict(type=kind, sessionId='fake-session-id', cwd='/home/dev/demo-app',
                    timestamp=(START + timedelta(minutes=minute)).isoformat(), **values)

    def codex(self, kind, minute=0, **payload):
        return dict(type=kind, timestamp=(START + timedelta(minutes=minute)).isoformat(), payload=payload)


class ClaudeTests(TemporaryLogs):
    def test_metrics_and_privacy(self):
        rows = [self.claude('user', message={'content':'SECRET_PROMPT_TEXT'}),
                self.claude('ai-title', aiTitle='Synthetic session title')]
        for minute, name in enumerate(('Read', 'Edit', 'Bash', 'Write'), 1):
            rows.append(self.claude('assistant', minute, isSidechain=minute==2, message={
                'id':f'm-{minute}', 'model':'synthetic-model',
                'usage':{'input_tokens':200, 'output_tokens':80,
                         'cache_read_input_tokens':800, 'cache_creation_input_tokens':50},
                'content':[{'type':'tool_use', 'id':f't-{minute}', 'name':name,
                            'input':{'file_path':f'/home/dev/demo-app/file-{minute}.py'}}]}))
            rows.append(self.claude('user', minute, message={'content':[{
                'type':'tool_result', 'tool_use_id':f't-{minute}', 'is_error':name=='Bash'}]}))
        path = self.write(rows)
        sessions = parse_claude(path)
        self.assertEqual(len(sessions), 1)
        s = sessions[0]
        self.assertEqual(s.user_prompts, 1)
        self.assertEqual(s.assistant_turns, 4)
        self.assertEqual(s.tools, {'Read': 1, 'Edit': 1, 'Bash': 1, 'Write': 1})
        self.assertEqual(s.failures, {'Bash': 1})
        self.assertEqual(s.tokens['input'], 800)
        self.assertEqual(s.tokens['output'], 320)
        self.assertEqual(s.tokens['cache_read'], 3200)
        self.assertEqual(s.tokens['cache_write'], 200)
        self.assertEqual(s.subagent_activity, 1)
        self.assertEqual(len(s.files), 2)
        self.assertIsNone(s.title)
        self.assertEqual(parse_claude(path, include_titles=True)[0].title, 'Synthetic session title')

    def test_unknown_malformed_and_unexpected_shapes(self):
        rows = [None, [], 42, self.claude('unknown', 0, message={'content': 'SECRET_PROMPT_TEXT'}),
                self.claude('assistant', 1, message=None), self.claude('user', 2, message={'content': [None, 3, []]}),
                self.claude('user', 3, message={'content': [{'type':'tool_result','tool_use_id': [], 'is_error':True}]}),
                self.claude('assistant', 4, message={'content': [{'type':'tool_use','name': [],'input':None}]})]
        path = self.write(rows)
        with path.open('a') as stream:
            stream.write('{malformed\n')
        result = parse_claude(path)
        self.assertEqual(len(result), 1)
        self.assertEqual(sum(result[0].tools.values()), 0)
        self.assertEqual(len(result[0].events), 4)

    def test_streaming_message_dedup_and_tool_result_exit(self):
        message = {'id':'same', 'model':'demo-model', 'usage':{'input_tokens':10,'output_tokens':2},
                   'content':[{'type':'tool_use','id':'call','name':'Bash','input':{}}]}
        rows = [self.claude('assistant', 0, message=message)]
        rows.append(self.claude('assistant', 1, message={**message, 'usage':{'input_tokens':10,'output_tokens':5}}))
        rows.extend([self.claude('user', 2, message={'content':[{'type':'tool_result','tool_use_id':'call',
                                                            'content':'Process exited with code 2'}]})]*2)
        s = parse_claude(self.write(rows))[0]
        self.assertEqual((s.assistant_turns, s.tools['Bash'], s.failures['Bash']), (1, 1, 1))
        self.assertEqual((s.tokens['input'], s.tokens['output']), (10, 5))


class CodexTests(TemporaryLogs):
    def test_calls_tokens_custom_patch_and_failures(self):
        rows = [self.codex('session_meta', id='synthetic-codex', cwd='/home/dev/demo-app',
                           source={'subagent':'synthetic-parent'}),
                self.codex('turn_context', model='synthetic-model'),
                self.codex('response_item', type='message', id='prompt', role='user'),
                self.codex('response_item', 1, type='custom_tool_call', name='apply_patch', call_id='patch',
                           input='*** Begin Patch\n*** Update File: src/main.py\n*** End Patch'),
                self.codex('response_item', 2, type='custom_tool_call_output', call_id='patch', output='Done'),
                self.codex('response_item', 3, type='function_call', name='exec_command', call_id='shell', arguments='{}'),
                self.codex('response_item', 4, type='function_call_output', call_id='shell', output={'exit_code':1}),
                self.codex('event_msg', 4, type='token_count', info={'total_token_usage':{
                    'input_tokens':1500, 'cached_input_tokens':1000, 'output_tokens':120, 'cache_write_input_tokens':30}}),
                self.codex('response_item', 5, type='message', id='answer', role='assistant')]
        s = parse_codex(self.write(rows))[0]
        self.assertEqual((s.user_prompts, s.assistant_turns), (1, 1))
        self.assertEqual(s.tools, {'apply_patch':1,'exec_command':1})
        self.assertEqual(s.failures, {'exec_command':1})
        self.assertEqual(s.tokens, {'input':500,'output':120,'cache_read':1000,'cache_write':30})
        self.assertEqual(s.files, {'/home/dev/demo-app/src/main.py'})
        self.assertEqual(s.models, {'synthetic-model'})
        self.assertGreater(s.subagent_activity, 0)

    def test_unknown_shapes_and_missing_info(self):
        rows = [None, [], {'type':'session_meta','payload':[]},
                self.codex('session_meta', id='fake-codex',cwd='/home/dev/demo-app'),
                self.codex('event_msg',1,type='token_count',info=None),
                self.codex('event_msg',2,type='token_count',info={'total_token_usage':{'input_tokens':'oops'}}),
                self.codex('response_item',3,type='function_call',name=None,arguments=[]),
                self.codex('response_item',4,type='message',role='user',content=None),
                self.codex('future_type',5,secret='SECRET_PROMPT_TEXT')]
        path = self.write(rows)
        with path.open('a') as stream:
            stream.write('not-json\n')
        s = parse_codex(path)[0]
        self.assertEqual(s.user_prompts, 1)
        self.assertEqual(sum(s.tokens.values()), 0)
        self.assertEqual(sum(s.tools.values()), 0)

    def test_error_correlation_last_usage_and_stale_snapshot(self):
        rows = [self.codex('session_meta',id='fake-codex',cwd='/home/dev/demo-app'),
                self.codex('response_item',1,type='function_call',name='shell',call_id='call',arguments='{}'),
                self.codex('response_item',2,type='function_call_output',call_id='call',output={'exit_code':1}),
                self.codex('event_msg',2,type='tool_error',call_id='call'),
                self.codex('event_msg',3,type='error'),
                self.codex('event_msg',4,type='token_count',info={'total_token_usage':{'input_tokens':100,'output_tokens':20}}),
                self.codex('event_msg',5,type='token_count',info={'total_token_usage':{'input_tokens':10,'output_tokens':2}}),
                self.codex('event_msg',6,type='token_count',info={'last_token_usage':{'input_tokens':5,'output_tokens':1}})]
        s = parse_codex(self.write(rows))[0]
        self.assertEqual(s.failures, {'shell':1,'(unattributed)':1})
        self.assertEqual((s.tokens['input'],s.tokens['output']), (105,21))

    def test_interleaved_counter_formats_do_not_multiply_usage(self):
        rows = [self.codex('session_meta',id='fake-codex')]
        for minute, (new, old) in enumerate(((110,100),(120,110),(130,120)), 1):
            rows.append(self.codex('token_usage_record',minute,thread_token_usage={'input_tokens':new}))
            rows.append(self.codex('event_msg',minute,type='token_count',info={'total_token_usage':{'input_tokens':old}}))
        s = parse_codex(self.write(rows))[0]
        self.assertEqual(s.tokens['input'],130)
        self.assertEqual(sum(day['input'] for day in s.daily_tokens.values()),130)

    def test_pre_window_cumulative_baseline(self):
        rows = [self.codex('session_meta',id='fake-codex'),
                self.codex('event_msg',1,type='token_count',info={'total_token_usage':{'input_tokens':100}}),
                self.codex('event_msg',10,type='token_count',info={'total_token_usage':{'input_tokens':150}})]
        s = parse_codex(self.write(rows), since=START+timedelta(minutes=5))[0]
        self.assertEqual(s.tokens['input'],50)


class MetricsTests(TemporaryLogs):
    def test_duration_cap_order_and_midnight(self):
        midnight = datetime(2026,10,7,tzinfo=UTC)
        s = Session('claude','fake',events=[midnight+timedelta(minutes=10),midnight-timedelta(minutes=1),midnight-timedelta(minutes=1)])
        self.assertEqual(s.active_seconds, 300)
        report = summarize([s])
        self.assertEqual([d['active_seconds'] for d in report['days']], [60,240])
        self.assertEqual(sum(d['active_seconds'] for d in report['days']),s.active_seconds)

    def test_since_until_project_and_mtime(self):
        dirs = {'claude':DEMO/'claude','codex':DEMO/'codex'}
        sessions = load_sessions(dirs, since=datetime(2026,10,5,tzinfo=UTC),
                                 until=datetime(2026,10,9,tzinfo=UTC), project='SAMPLE-API')
        self.assertEqual(len(sessions),2)
        self.assertEqual({s.start.day for s in sessions}, {5,7})
        path = self.write([self.claude('user',message={'content':'fake'})])
        os.utime(path,(1,1))
        self.assertEqual(list(discover(self.root,'claude',START)),[])

    def test_home_redaction_and_opt_ins(self):
        self.assertEqual(redact_home('/home/dev/a','/home/dev'),'~/a')
        self.assertEqual(redact_home('/home/developer/a','/home/dev'),'/home/developer/a')
        self.assertEqual(redact_home('/home/dev','/home/dev'),'~')
        self.assertEqual(redact_home('Title: /home/dev/app','/home/dev'),'Title: ~/app')
        home = str(Path.home())
        s = Session('claude','fake',cwd=home+'/demo-app',events=[START],files={home+'/demo-app/code.py'},title='Demo title')
        default = summarize([s])
        serialized = json.dumps(default)
        self.assertNotIn(home,serialized)
        self.assertNotIn('code.py',serialized)
        self.assertNotIn('Demo title',serialized)
        opted = summarize([s],full_paths=True,include_titles=True)
        self.assertEqual(opted['sessions'][0]['files'],['~/demo-app/code.py'])
        self.assertEqual(opted['sessions'][0]['title'],'Demo title')
        self.assertNotIn(home,json.dumps(opted))
        self.assertEqual(summarize([Session('claude','fake',cwd=home,events=[START])])['sessions'][0]['project'],'~')

    def test_same_basename_projects_are_separate(self):
        sessions = [Session('claude',str(i),cwd=path,events=[START])
                    for i,path in enumerate(('/home/dev/a/app','/home/dev/b/app'))]
        self.assertEqual(len(summarize(sessions)['projects']),2)

    def test_render_and_json_never_contain_raw_text(self):
        sessions = load_sessions({'claude':DEMO/'claude','codex':DEMO/'codex'},include_titles=True)
        for full_paths in (False,True):
            for titles in (False,True):
                report = summarize(sessions,full_paths,titles)
                html = render_html(report)
                self.assertNotIn('SECRET_PROMPT_TEXT',html+json.dumps(report))
                self.assertIn('<!doctype html>',html)
                self.assertIn(f"{report['totals']['tool_calls']:,}",html)
                self.assertIn('Totals',html)
                self.assertIn('prefers-color-scheme:dark',html)
                self.assertNotIn('<script src=',html)
                parser = HTMLParser(convert_charrefs=True)
                parser.feed(html)
                parser.close()
        malicious = Session('claude','fake',cwd='/home/dev/<script>alert(1)</script>',events=[START],title='</script><img src=x>')
        html = render_html(summarize([malicious],include_titles=True,full_paths=True))
        self.assertNotIn('<img src=x>',html)
        self.assertIn('&lt;img src=x&gt;',html)


class ChartTests(unittest.TestCase):
    def test_nice_hours_ticks(self):
        ticks = nice_ticks(5.82806, 'hours')
        self.assertEqual(ticks[-1][0], 10)
        self.assertEqual([label for _, label in ticks], ['0', '2.5', '5', '7.5', '10'])
        for maximum in (0.01, 1, 1.9, 2.4, 4.9, 5.82806, 25, 99):
            with self.subTest(maximum=maximum):
                ticks = nice_ticks(maximum, 'hours')
                self.assertGreaterEqual(ticks[-1][0], maximum)
                labels = [label for _, label in ticks]
                self.assertEqual(len(labels), len(set(labels)))
                for label in labels:
                    self.assertRegex(label, r'^\d+(?:\.\d)?$')

    def test_nice_zero_ticks_and_integer_counts(self):
        for mode in ('hours', 'tokens', 'sessions', 'counts'):
            with self.subTest(mode=mode):
                ticks = nice_ticks(0, mode)
                self.assertEqual(ticks[0], (0, '0'))
                self.assertEqual(ticks[-1], (1, '1'))
        for maximum in (1, 2, 3, 5, 24, 101, 1234567):
            with self.subTest(maximum=maximum):
                ticks = nice_ticks(maximum, 'counts')
                self.assertGreaterEqual(ticks[-1][0], maximum)
                self.assertTrue(all(value == int(value) for value, _ in ticks))
                self.assertTrue(all(label == f'{value:,.0f}' for value, label in ticks))

    def test_nice_token_ticks_are_compact(self):
        ticks = nice_ticks(1234567, 'tokens')
        self.assertEqual(ticks[-1], (2000000, '2.0M'))
        self.assertEqual(tick_label(1234567, 'tokens'), '1.2M')
        self.assertTrue(all(len(label) <= 6 for _, label in ticks))

    def test_daily_svg_labels_fit_and_bars_use_rounded_scale(self):
        for mode, value in (('hours', 5.82806), ('tokens', 1234567), ('sessions', 1234567),
                            ('hours', 0), ('tokens', 0), ('sessions', 0)):
            with self.subTest(mode=mode, value=value):
                day = dict(date='2026-10-05', active_seconds=value * 3600, sessions=value,
                           tokens=dict(input=value // 2, output=value - value // 2,
                                       cache_read=0, cache_write=0))
                svg = ET.fromstring(daily_chart([day], mode))
                labels = [node for node in svg.findall('text') if node.get('text-anchor') == 'end']
                ticks = nice_ticks(value, mode)
                self.assertEqual([node.text for node in labels], [label for _, label in ticks])
                for node in labels:
                    self.assertGreaterEqual(float(node.get('x')) - len(node.text) * 12, 10)
                bars = svg.findall('rect')
                self.assertAlmostEqual(sum(float(bar.get('height')) for bar in bars),
                                       165 * value / ticks[-1][0], places=1)
                self.assertTrue(all(float(bar.get('y')) >= 30 for bar in bars))

    def test_tool_svg_labels_fit_and_use_rounded_scale(self):
        name = 'W' * 30
        for failure in (False, True):
            with self.subTest(failure=failure):
                svg = ET.fromstring(bar_chart({name: 1234567}, 'Tools', failure=failure))
                name_label, count_label = svg.findall('text')
                self.assertGreaterEqual(float(name_label.get('x')) - len(name_label.text) * 12, 10)
                self.assertEqual(count_label.text, '1,234,567')
                self.assertLessEqual(float(count_label.get('x')) + len(count_label.text) * 12, 630)
                bar = svg.find('rect')
                available = 640 - float(bar.get('x')) - len(count_label.text) * 12 - 20
                self.assertAlmostEqual(float(bar.get('width')), available * 1234567 / 2000000, places=2)


class DemoTests(unittest.TestCase):
    def test_fixed_fortnight_diversity_and_size(self):
        sessions = load_sessions({source:DEMO/source for source in ('claude','codex')})
        report = summarize(sessions)
        self.assertEqual(len(sessions), 24)
        self.assertEqual({s.source for s in sessions}, {'claude','codex'})
        self.assertEqual([d['date'] for d in report['days']],
                         [(datetime(2026,9,28)+timedelta(days=n)).date().isoformat() for n in range(14)])
        self.assertEqual([d['sessions'] for d in report['days']], [2,1,3,0,2,1,0,5,2,1,3,0,2,2])
        self.assertEqual({p['project'] for p in report['projects']},
                         {'web-shop','sample-api','docs-site','data-pipeline','mobile-app'})
        self.assertTrue({'Read','Bash','Edit','Grep','exec_command','apply_patch','Write',
                         'TodoWrite','WebFetch','Task'} <= report['tools'].keys())
        self.assertGreater(len(set(report['tools'].values())), 6)
        self.assertGreater(len({sum(s.tools.values()) for s in sessions}), 8)
        self.assertGreater(len({s.active_seconds for s in sessions}), 8)
        self.assertTrue(any(s.subagent_activity for s in sessions if s.source=='claude'))
        self.assertTrue(any(s.subagent_activity for s in sessions if s.source=='codex'))
        totals = report['totals']
        self.assertGreater(totals['tokens']['cache_read'] / totals['total_tokens'], .7)
        self.assertTrue(all(totals['tokens'][key] > 0 for key in ('input','output','cache_read','cache_write')))
        self.assertGreater(totals['failed_tool_calls'], 0)
        self.assertLess(totals['failure_rate'], .1)
        self.assertLess(sum(path.stat().st_size for path in DEMO.rglob('*') if path.is_file()), 400_000)


class CLITests(TemporaryLogs):
    def run_cli(self,*args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = main(list(args))
        return code,output.getvalue()

    def test_demo_module_entrypoint_and_json(self):
        html,json_path = self.root/'report.html',self.root/'report.json'
        result = subprocess.run([sys.executable,'-m','agent_run_report','--demo','--out',str(html),'--json',str(json_path)],
                                text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('24 sessions',result.stdout)
        self.assertTrue(html.is_file())
        report = json.loads(json_path.read_text())
        self.assertEqual(report['totals']['tool_calls'],376)
        self.assertNotIn('SECRET_PROMPT_TEXT',html.read_text()+json_path.read_text())

    def test_empty_dirs(self):
        code,output = self.run_cli('--claude-dir',str(self.root),'--codex-dir',str(self.root))
        self.assertEqual(code,1)
        self.assertIn('No matching sessions',output)
        self.assertIn('Looked in:',output)

    def test_bad_args(self):
        for args in [('--since','yesterday'),('--since','2026-02-30'),('--since','0d'),
                     ('--since','2026-10-15','--until','2026-10-01'),('--out','same','--json','same')]:
            with self.subTest(args=args),contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit) as exc:
                main(args)
            self.assertEqual(exc.exception.code,2)

    def test_source_project_and_until(self):
        html = self.root/'report.html'
        code,output = self.run_cli('--demo','--source','claude','--project','SAMPLE-API','--until','2026-10-06','--out',str(html))
        self.assertEqual(code,0)
        self.assertIn('2 sessions',output)
        self.assertNotIn('codex-demo-model',html.read_text())

    def test_version(self):
        with contextlib.redirect_stdout(io.StringIO()),self.assertRaises(SystemExit) as exc:
            main(['--version'])
        self.assertEqual(exc.exception.code,0)
        self.assertEqual(__version__,'0.1.0')


if __name__ == '__main__':
    unittest.main()
