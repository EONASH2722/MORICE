from pathlib import Path
import json
import os
import subprocess
import sys
import threading
import tempfile
import unittest
from unittest.mock import Mock, patch

from morice import llm_client


class LlmCompletionTests(unittest.TestCase):
    def test_supported_auto_gpu_environment_can_import_the_client(self):
        for setting in ('auto','all'):
            with self.subTest(setting=setting):
                result=subprocess.run([sys.executable,'-c','from morice.llm_client import DEFAULT_GPU_LAYERS;print(DEFAULT_GPU_LAYERS)'],
                    cwd=Path(__file__).resolve().parents[1],env={**os.environ,'MORICE_GPU_LAYERS':setting},capture_output=True,text=True,check=True,timeout=20)
                self.assertEqual(result.stdout.strip(),'0')

    def test_reasoning_only_stream_retries_once_with_same_prompt_for_visible_answer(self):
        payload={'messages':[{'role':'user','content':'Calculate the result.'}],'max_tokens':96,'chat_template_kwargs':{'enable_thinking':True}}
        first=[{'choices':[{'delta':{'reasoning_content':'Owned synthetic reasoning fixture'}}]},
            {'choices':[{'delta':{},'finish_reason':'length'}]}]
        second=[{'choices':[{'delta':{'content':'The result is 56.'}}]},{'choices':[{'delta':{},'finish_reason':'stop'}]}]
        with patch.object(llm_client,'_post_stream_json',side_effect=(iter(first),iter(second))) as request:
            answer=''.join(llm_client._try_openai_chat_stream('http://local',payload,10))
        self.assertEqual(answer,'The result is 56.')
        self.assertEqual(request.call_count,2)
        retry=request.call_args_list[1].args[1]
        self.assertEqual(retry['messages'],payload['messages'])
        self.assertEqual(retry['reasoning_budget_tokens'],0)
        self.assertFalse(retry['chat_template_kwargs']['enable_thinking'])
        self.assertTrue(payload['chat_template_kwargs']['enable_thinking'])

    def test_cancelled_reasoning_stream_does_not_retry(self):
        cancellation=threading.Event()
        def events(*args):
            yield {'choices':[{'delta':{'reasoning_content':'Owned fixture'}}]}
            cancellation.set()
            yield {'choices':[{'delta':{},'finish_reason':'length'}]}
        with patch.object(llm_client,'_post_stream_json',side_effect=events) as request:
            self.assertEqual(''.join(llm_client._try_openai_chat_stream('http://local',{'messages':[]},10,cancellation)),'')
        self.assertEqual(request.call_count,1)

    def test_reasoning_only_sync_retries_without_fabricating_conversation(self):
        payload={'messages':[{'role':'user','content':'Calculate it.'}],'chat_template_kwargs':{'enable_thinking':True}}
        replies=[{'choices':[{'message':{'content':'','reasoning_content':'Owned fixture'},'finish_reason':'length'}]},
            {'choices':[{'message':{'content':'56'},'finish_reason':'stop'}]}]
        with patch.object(llm_client,'_post_json',side_effect=replies) as request:
            self.assertEqual(llm_client._try_openai_chat('http://local',payload,10),'56')
        self.assertEqual(request.call_count,2)
        self.assertEqual(request.call_args.args[1]['messages'],payload['messages'])

    def test_installed_qwen35_preferred_and_explicit_or_older_selections_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);models=root/'models/llm';models.mkdir(parents=True)
            preferred=models/llm_client.PREFERRED_REASONING_GGUF;preferred.write_bytes(b'GGUF')
            older=root/llm_client.DEFAULT_BUNDLED_GGUF;older.write_bytes(b'GGUF')
            with patch('morice.config.local_data_dir',return_value=root), \
                patch.object(llm_client,'_project_path',side_effect=lambda *parts:str(root.joinpath(*parts))), \
                patch.object(llm_client,'_asset_path',side_effect=lambda *parts:str(root.joinpath('assets',*parts))), \
                patch.object(llm_client,'DEFAULT_GGUF',''),patch.object(llm_client,'DEFAULT_MODEL',''):
                self.assertEqual(llm_client._resolve_gguf_path(),str(preferred))
                self.assertEqual(llm_client._resolve_gguf_path(str(older)),str(older))
                preferred.unlink()
                self.assertEqual(llm_client._resolve_gguf_path(),str(older))

    def test_strict_template_gets_one_system_role_on_sync_and_stream_wire(self):
        messages=[{'role':'system','content':'Core policy.'},{'role':'system','content':'Saved preferences and context.'},
            {'role':'user','content':'Original question.'},{'role':'assistant','content':'Earlier reply.'},{'role':'user','content':'Latest request.'}]
        payload={'messages':messages,'temperature':.2}
        for streaming in (False,True):
            response=Mock();response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
            response.read.return_value=b'{"ok": true}';response.__iter__=Mock(return_value=iter((b'data: {"ok":true}\n',b'data: [DONE]\n')))
            with patch.object(llm_client.urllib.request,'urlopen',return_value=response) as request:
                if streaming:list(llm_client._post_stream_json('http://local/v1/chat/completions',payload,10))
                else:llm_client._post_json('http://local/v1/chat/completions',payload,10)
            sent=json.loads(request.call_args.args[0].data)
            self.assertEqual([m['role'] for m in sent['messages']],['system','user','assistant','user'])
            self.assertEqual(sent['messages'][0]['content'],'Core policy.\n\nSaved preferences and context.')
            self.assertEqual(sent['messages'][1:],messages[2:])
            self.assertEqual(len(payload['messages']),5)

    def test_prewarm_loads_selected_gguf_without_generating(self):
        with tempfile.TemporaryDirectory() as directory:
            model = Path(directory) / "fast.gguf"
            model.touch()
            with patch.object(
                llm_client,
                "ensure_server",
                return_value="http://127.0.0.1:8080",
            ) as ensure:
                endpoint = llm_client.prewarm_local_model(str(model))

        self.assertEqual(endpoint, "http://127.0.0.1:8080")
        self.assertEqual(ensure.call_count, 1)

    def test_prefix_prime_disables_reasoning_and_uses_stable_system(self):
        with tempfile.TemporaryDirectory() as directory:
            model = Path(directory) / "fast.gguf"
            model.touch()
            captured = {}

            def stream(_url, payload, _timeout, telemetry=None):
                captured.update(payload)
                if telemetry is not None:
                    telemetry(
                        "model_usage",
                        {
                            "usage": {
                                "prompt_tokens": 100,
                                "completion_tokens": 1,
                            }
                        },
                    )
                yield "Ready"

            with (
                patch.object(llm_client, "ensure_server", return_value="http://local"),
                patch.object(llm_client, "_try_openai_chat_stream", side_effect=stream),
            ):
                result = llm_client.prime_local_chat_prefix(
                    str(model),
                    extra_system="Stable user preferences.",
                )

        self.assertTrue(result["ready"])
        self.assertEqual(result["promptTokens"], 100)
        self.assertEqual(captured["reasoning_budget"], 0)
        self.assertFalse(captured["chat_template_kwargs"]["enable_thinking"])
        self.assertEqual(captured["messages"][1]["content"], "Stable user preferences.")

    def test_local_server_timeout_is_not_retried_for_another_long_wait(self):
        with (
            patch.object(llm_client, "_resolve_gguf_path", return_value="model.gguf"),
            patch.object(llm_client, "ensure_server", return_value="http://local"),
            patch.object(
                llm_client,
                "_try_openai_chat",
                side_effect=TimeoutError("timed out"),
            ) as completion,
        ):
            reply = llm_client.chat([], "hello", gguf_path="model.gguf")

        self.assertEqual(completion.call_count, 1)
        self.assertIn("took too long", reply)

    def test_openai_stream_yields_deltas_before_completion(self):
        events = iter(
            [
                {"choices": [{"delta": {"content": "MORICE "}}]},
                {"choices": [{"delta": {"content": "online."}}]},
                {"choices": [{"delta": {}, "finish_reason": "stop"}]},
            ]
        )
        with patch.object(llm_client, "_post_stream_json", return_value=events):
            stream = llm_client._try_openai_chat_stream(
                "http://local",
                {"messages": []},
                10,
            )
            self.assertEqual(next(stream), "MORICE ")
            self.assertEqual("".join(stream), "online.")

    def test_openai_stream_reports_backend_first_token_and_usage(self):
        events = iter(
            [
                {"choices": [{"delta": {"content": " "}}]},
                {"choices": [{"delta": {"content": "Useful"}}]},
                {
                    "choices": [{"delta": {}, "finish_reason": "stop"}],
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 2,
                        "total_tokens": 12,
                    },
                },
            ]
        )
        observed = []

        def telemetry(event, payload):
            observed.append((event, payload))

        with patch.object(llm_client, "_post_stream_json", return_value=events):
            output = "".join(
                llm_client._try_openai_chat_stream(
                    "http://local",
                    {"messages": []},
                    10,
                    telemetry=telemetry,
                )
            )

        self.assertEqual(output, " Useful")
        names = [event for event, _payload in observed]
        self.assertEqual(names.count("model_first_useful_token"), 1)
        self.assertIn("model_usage", names)
        self.assertEqual(names[-1], "model_stream_complete")

    def test_stream_parser_accepts_sse_and_ndjson_and_stops_on_cancel(self):
        response = Mock()
        response.__enter__ = Mock(return_value=iter((
            b'data: {"value": 1}\n',
            b'{"value": 2}\n',
            b'data: [DONE]\n',
        )))
        response.__exit__ = Mock(return_value=False)
        with patch.object(llm_client.urllib.request, "urlopen", return_value=response):
            values = list(llm_client._post_stream_json("http://local", {}, 10))
        self.assertEqual(values, [{"value": 1}, {"value": 2}])

    def test_ollama_stream_uses_streaming_payload(self):
        captured = {}

        def events(_url, payload, _timeout, _cancel):
            captured.update(payload)
            yield {"message": {"content": "first"}, "done": False}
            yield {"message": {"content": " second"}, "done": True}

        with patch.object(llm_client, "_post_stream_json", side_effect=events):
            result = "".join(
                llm_client._try_ollama_messages_stream(
                    "http://local", [], "model", 10, 0.2, 0.9
                )
            )
        self.assertTrue(captured["stream"])
        self.assertEqual(result, "first second")

    def test_ollama_modelfile_matches_long_reply_runtime_limits(self):
        modelfile = (
            Path(__file__).resolve().parents[1] / "Modelfile"
        ).read_text(encoding="utf-8")
        self.assertIn(f"PARAMETER num_ctx {llm_client.DEFAULT_CTX}", modelfile)
        self.assertIn(
            f"PARAMETER num_predict {llm_client.DEFAULT_MAX_TOKENS}",
            modelfile,
        )

    def test_openai_length_finish_is_continued_without_duplicate_overlap(self):
        responses = [
            {
                "choices": [
                    {
                        "message": {"content": "First section.\nShared ending"},
                        "finish_reason": "length",
                    }
                ]
            },
            {
                "choices": [
                    {
                        "message": {
                            "content": "Shared ending and the completed second section."
                        },
                        "finish_reason": "stop",
                    }
                ]
            },
        ]
        payload = {
            "messages": [{"role": "user", "content": "Write a complete report."}],
            "max_tokens": 64,
        }

        with patch.object(llm_client, "_post_json", side_effect=responses) as post:
            result = llm_client._try_openai_chat("http://local", payload, 10)

        self.assertEqual(post.call_count, 2)
        self.assertEqual(result.count("Shared ending"), 1)
        self.assertTrue(result.endswith("completed second section."))

    def test_context_fitting_preserves_system_and_latest_user_message(self):
        huge_history = [
            {"role": "system", "content": "SYSTEM RULES"},
            *[
                {"role": "assistant", "content": f"old-{index}-" + ("x" * 2000)}
                for index in range(40)
            ],
            {"role": "user", "content": "LATEST REQUEST"},
        ]

        fitted = llm_client._fit_messages_to_context(huge_history)

        self.assertEqual(fitted[0]["content"], "SYSTEM RULES")
        self.assertEqual(fitted[-1]["content"], "LATEST REQUEST")
        self.assertLess(
            sum(len(message["content"]) for message in fitted),
            sum(len(message["content"]) for message in huge_history),
        )

    def test_local_stream_disables_hidden_reasoning_by_default(self):
        captured = {}

        def stream(_url, payload, _timeout, _cancel):
            captured.update(payload)
            yield "Visible immediately."

        model = Path(__file__).with_suffix(".gguf")
        model.write_bytes(b"GGUF")
        try:
            with (
                patch.object(llm_client, "ensure_server", return_value="http://local"),
                patch.object(llm_client, "_try_openai_chat_stream", side_effect=stream),
            ):
                output = "".join(
                    llm_client.stream_chat([], "hello", gguf_path=str(model))
                )
        finally:
            model.unlink(missing_ok=True)

        self.assertEqual(output, "Visible immediately.")
        self.assertEqual(captured["reasoning_budget"], 0)
        self.assertFalse(captured["chat_template_kwargs"]["enable_thinking"])

    def test_deep_local_stream_can_enable_reasoning(self):
        captured = {}

        def stream(_url, payload, _timeout, _cancel):
            captured.update(payload)
            yield "Deep answer."

        model = Path(__file__).with_suffix(".gguf")
        model.write_bytes(b"GGUF")
        try:
            with (
                patch.object(llm_client, "ensure_server", return_value="http://local"),
                patch.object(llm_client, "_try_openai_chat_stream", side_effect=stream),
            ):
                "".join(
                    llm_client.stream_chat(
                        [],
                        "derive this",
                        gguf_path=str(model),
                        enable_reasoning=True,
                    )
                )
        finally:
            model.unlink(missing_ok=True)

        self.assertEqual(captured["reasoning_budget"], -1)
        self.assertGreater(captured['reasoning_budget_tokens'],0)
        self.assertLess(captured['reasoning_budget_tokens'],captured['max_tokens'])
        self.assertTrue(captured["chat_template_kwargs"]["enable_thinking"])

    def test_deep_stream_honors_context_and_output_budget(self):
        captured={}
        prompt='Independent technical assessment: '+('supplied engineering parameters; '*350)
        def stream(_url,payload,_timeout,_cancel):
            captured.update(payload);yield 'An answer.'
        def tokenize(url,payload,_timeout):
            if url.endswith('/apply-template'):
                return {'prompt':''.join(m['content'] for m in payload['messages'])}
            return {'tokens':range(len(payload['content'])//4)}
        model=Path(self.id().replace('.','_')+'.gguf')
        model.write_bytes(b'GGUF')
        try:
            with patch.object(llm_client,'ensure_server',return_value='http://local') as ensure, \
                 patch.object(llm_client,'_post_json',side_effect=tokenize), \
                 patch.object(llm_client,'_try_openai_chat_stream',side_effect=stream):
                output=''.join(llm_client.stream_chat([],prompt,gguf_path=str(model),
                    context_tokens=16384,max_tokens=4096,enable_reasoning=True))
            self.assertEqual(output,'An answer.')
            self.assertEqual(ensure.call_args.args[1],16384)
            self.assertEqual(captured['max_tokens'],4096)
            self.assertEqual(captured['messages'][-1]['content'],prompt)
        finally:model.unlink(missing_ok=True)

    def test_oversized_current_request_is_reported_instead_of_excerpted(self):
        messages=[{'role':'system','content':'Core instruction.'},{'role':'user','content':'x'*10000}]
        with self.assertRaisesRegex(ValueError,'no part of it was silently omitted'):
            llm_client._fit_messages_to_context(messages,context_tokens=2048,max_output_tokens=512)


if __name__ == "__main__":
    unittest.main()
