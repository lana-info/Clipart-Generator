import copy
import json
import unittest
from unittest.mock import patch, MagicMock

import requests

from studio_clipart_recipe import ClipartRecipe
from studio_clipart_objects import fill_recipe, TEXT_FIELDS
from studio_text_client import generate_plan, parse_text_response, TextGenerationError
from studio_text_models import text_models_for, resolve_text_model


class TextClientTests(unittest.TestCase):
    def setUp(self):
        self.recipe = ClipartRecipe(theme='Мишки и самолёты')
        self.recipe.objects = fill_recipe([], self.recipe.counts)
        self.recipe.objects[0].update(name='Закреплённый мишка', pinned=True)
        self.rows = [dict(id=item['id'], **dict.fromkeys(TEXT_FIELDS, 'деталь'))
                     for item in self.recipe.objects[1:]]
        self.data = dict(choices=[dict(finish_reason='stop', message=dict(
            content=json.dumps(dict(items=self.rows))))])
        self.args = dict(provider='openrouter', model='openai/gpt-5-mini',
                         api_key='dummy-test-key', approved=True)

    def mock_response(self, post, data=None, status=200):
        response = MagicMock()
        response.status_code = status
        response.iter_content.return_value = [json.dumps(self.data if data is None else data).encode()]
        post.return_value.__enter__.return_value = response
        return response

    def test_catalog_has_only_approved_routes(self):
        self.assertEqual(len(text_models_for('kie')), 2)
        self.assertEqual(len(text_models_for('openrouter')), 9)
        self.assertTrue(resolve_text_model('openrouter', 'deepseek/deepseek-v4-flash-vision-exp').experimental)
        for provider, model in [('kie', 'openai/gpt-5-mini'), ('openrouter', 'openai/gpt-5.4-mini')]:
            with self.assertRaises(ValueError):
                resolve_text_model(provider, model)

    @patch('studio_text_client.requests.post')
    def test_explicit_launch_and_key_guard(self, post):
        for overrides in [dict(approved=False), dict(api_key=''), dict(api_key='bad\nkey')]:
            with self.assertRaises(TextGenerationError):
                generate_plan(self.recipe, **(self.args | overrides))
        post.assert_not_called()

    @patch('studio_text_client.requests.post')
    def test_openrouter_plan_is_atomic_and_no_fallback(self, post):
        self.mock_response(post)
        before = copy.deepcopy(self.recipe.to_dict())
        result = generate_plan(self.recipe, **self.args)
        self.assertEqual(before, self.recipe.to_dict())
        self.assertEqual(result['items'][0], self.recipe.objects[0])
        self.assertEqual(result['items'][1]['name'], 'деталь')
        post.assert_called_once()
        payload = post.call_args.kwargs['json']
        self.assertEqual(payload['model'], 'openai/gpt-5-mini')
        self.assertFalse(payload['provider']['allow_fallbacks'])
        self.assertEqual(payload['response_format']['type'], 'json_schema')
        self.assertNotIn('tools', payload)
        self.assertFalse(post.call_args.kwargs['allow_redirects'])

    @patch('studio_text_client.requests.post')
    def test_holiday_guidance_reaches_provider_as_bounded_design_data(self, post):
        self.recipe.theme = 'Мишки Тедди'
        self.recipe.context = 'Christmas'
        self.mock_response(post)
        generate_plan(self.recipe, **self.args)
        payload = post.call_args.kwargs['json']
        self.assertIn('holiday guidance', payload['messages'][0]['content'])
        brief = json.loads(payload['messages'][1]['content'])
        self.assertEqual(brief['brief']['theme'], 'Мишки Тедди')
        self.assertEqual(brief['holiday']['holiday'], 'Рождество')
        self.assertIn('gift box', brief['holiday']['props'])
        self.assertNotIn('Mother', str(brief['holiday']))

    @patch('studio_text_client.requests.post')
    def test_kie_native_envelope_and_model_specific_url(self, post):
        native = dict(candidates=[dict(finishReason='STOP', content=dict(parts=[
            dict(thought=True, text='not final'), dict(text=json.dumps(dict(items=self.rows)))]))])
        self.mock_response(post, native)
        result = generate_plan(self.recipe, **(self.args | dict(provider='kie', model='gemini-3-8-flash-openai')))
        self.assertEqual(len(result['items']), self.recipe.total)
        self.assertEqual(post.call_args.args[0], 'https://api.kie.ai/gemini-3-8-flash-openai/v1/chat/completions')
        self.assertNotIn('response_format', post.call_args.kwargs['json'])

    @patch('studio_text_client.requests.post')
    def test_style_guidance_is_explicitly_respected_by_planning_prompt(self, post):
        self.recipe.visual = {'technique': 'Акварель', 'mood': 'Нежное'}
        self.mock_response(post)
        generate_plan(self.recipe, **self.args)
        instructions = post.call_args.kwargs['json']['messages'][0]['content'].casefold()
        self.assertIn('style guidance', instructions)
        self.assertIn('keep one coherent base style', instructions)

    @patch('studio_text_client.requests.post')
    def test_commercial_guidance_reaches_planner_instructions(self, post):
        self.mock_response(post)
        generate_plan(self.recipe, **self.args)
        instructions = post.call_args.kwargs['json']['messages'][0]['content'].casefold()
        self.assertIn('commercial guidance', instructions)
        self.assertIn('no filler', instructions)
        self.assertIn('near duplicates', instructions)
        self.assertIn('clean interior opening', instructions)
        self.assertIn('floating fragments', instructions)


    @patch('studio_text_client.requests.post')
    def test_network_failure_is_not_retried_or_leaked(self, post):
        post.side_effect = requests.Timeout('dummy-test-key private request data')
        with self.assertRaises(TextGenerationError) as raised:
            generate_plan(self.recipe, **self.args)
        self.assertNotIn('dummy-test-key', str(raised.exception))
        post.assert_called_once()

    @patch('studio_text_client.requests.post')
    def test_http_errors_redirects_and_oversize(self, post):
        for code in (302, 401, 429, 500):
            self.mock_response(post, status=code)
            with self.assertRaises(TextGenerationError):
                generate_plan(self.recipe, **self.args)
        response = self.mock_response(post)
        response.iter_content.return_value = [b'x' * 2_000_001]
        with self.assertRaises(TextGenerationError):
            generate_plan(self.recipe, **self.args)

    def test_bad_envelopes_refusals_and_truncation(self):
        bad = [None, [], {}, dict(choices=[]), dict(choices=[dict(message=[])])]
        for reason in ('length', 'tool_calls', 'content_filter'):
            data = copy.deepcopy(self.data)
            data['choices'][0]['finish_reason'] = reason
            bad.append(data)
        for content in ('not json', '[]', ''):
            bad.append(dict(choices=[dict(finish_reason='stop', message=dict(content=content))]))
        for data in bad:
            with self.subTest(data=data), self.assertRaises(TextGenerationError):
                parse_text_response(data, 'openrouter')

    @patch('studio_text_client.requests.post')
    def test_invalid_ideas_leave_draft_unchanged(self, post):
        self.rows[0]['id'] = 'invented'
        self.data['choices'][0]['message']['content'] = json.dumps(dict(items=self.rows))
        self.mock_response(post)
        before = self.recipe.to_dict()
        with self.assertRaises(TextGenerationError):
            generate_plan(self.recipe, **self.args)
        self.assertEqual(before, self.recipe.to_dict())


    @patch('studio_text_client.requests.post')
    def test_openrouter_reference_image_payload_has_no_local_path(self, post):
        import tempfile
        from pathlib import Path
        from PIL import Image
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'secret-local-name.png'
            Image.new('RGB', (16, 16), (10, 20, 30)).save(path)
            self.recipe.references = [dict(path=str(path), roles=['character'], notes='round teddy face')]
            from studio_clipart_references import reference_image_upload_info
            fingerprint = reference_image_upload_info(path)['sha256']
            self.mock_response(post)
            generate_plan(
                self.recipe, **self.args, reference_images=[str(path)],
                reference_images_approved=True,
                reference_image_hashes={str(path.resolve()): fingerprint},
                input_modalities=('text', 'image'),
            )
            payload = post.call_args.kwargs['json']
            content = payload['messages'][1]['content']
            self.assertIsInstance(content, list)
            self.assertEqual(content[0]['type'], 'text')
            self.assertEqual(content[1]['type'], 'image_url')
            self.assertTrue(content[1]['image_url']['url'].startswith('data:image/png;base64,'))
            encoded = json.dumps(payload)
            self.assertNotIn(str(path), encoded)
            self.assertNotIn('secret-local-name', encoded)
            self.assertEqual(payload['provider']['data_collection'], 'deny')

    @patch('studio_text_client.requests.post')
    def test_reference_image_handoff_requires_exact_preflight_fingerprint(self, post):
        import tempfile
        from pathlib import Path
        from PIL import Image
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'reference.png'
            Image.new('RGB', (12, 12), (1, 2, 3)).save(path)
            self.recipe.references = [dict(path=str(path), roles=['character'], notes='')]
            with self.assertRaisesRegex(TextGenerationError, 'отпечат'):
                generate_plan(
                    self.recipe, **self.args, reference_images=[str(path)],
                    reference_images_approved=True, input_modalities=('text', 'image'),
                )
            post.assert_not_called()

    def test_reference_images_require_explicit_approval_and_capability(self):
        import tempfile
        from pathlib import Path
        from PIL import Image
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'reference.png'
            Image.new('RGB', (12, 12), (1, 2, 3)).save(path)
            for extra in (
                dict(reference_images=[str(path)], reference_images_approved=False,
                     input_modalities=('text', 'image')),
                dict(reference_images=[str(path)], reference_images_approved=True,
                     input_modalities=('text',)),
            ):
                with self.subTest(extra=extra), self.assertRaises(TextGenerationError):
                    generate_plan(self.recipe, **self.args, **extra)


def test_kie_claude_native_body_and_reply():
    case = TextClientTests()
    case.setUp()
    with patch('studio_text_client.requests.post') as post:
        case.mock_response(post, dict(stop_reason='end_turn', content=[
            dict(type='thinking', thinking='private'),
            dict(type='text', text=json.dumps(dict(items=case.rows)))]))
        result = generate_plan(case.recipe, **(case.args | dict(provider='kie', model='claude-sonnet-4-6')))
        body = post.call_args.kwargs['json']
        assert post.call_args.args[0] == 'https://api.kie.ai/claude/v1/messages'
        assert body['model'] == 'claude-sonnet-4-6'
        assert body['max_tokens'] == 16000
        assert body['messages'][0]['role'] == 'user'
        assert 'provider' not in body
        assert len(result['items']) == case.recipe.total
    for reason in ('max_tokens', 'tool_use', 'refusal'):
        with unittest.TestCase().assertRaises(TextGenerationError):
            parse_text_response(dict(stop_reason=reason, content=[dict(type='text', text='{}')]), 'kie')
