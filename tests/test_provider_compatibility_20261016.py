import tempfile
import unittest
from unittest.mock import Mock, patch
from gpt25_provider import task_result
from fal_model_catalog import fal_generation_payload, fal_endpoint_profiles
from model_catalog import model_spec, validate_generation_contract
from studio_text_models import resolve_text_model
from studio_prompt_composer_api import resolve_composer_model
from tests.test_gpt25_async_worker import OfflineWorker, namespace

class ProviderCompatibilityTests(unittest.TestCase):
    def test_qwen_uses_openrouter_model_id_in_both_catalogs(self):
        model='qwen/qwen3.5-397b-a17b'
        for resolver in (resolve_text_model, resolve_composer_model):
            with self.subTest(resolver=resolver.__name__):
                self.assertEqual(resolver('openrouter',model).model,model)
                with self.assertRaises(ValueError):
                    resolver('openrouter',model+'-20260216')

    def test_atlascloud_documented_succeeded_status_returns_image(self):
        self.assertEqual(task_result('atlascloud',{'data':{'status':'succeeded','outputs':['https://images.example.org/image.png']}}),('completed','https://images.example.org/image.png'))

    def test_piapi_unknown_success_alias_does_not_accept_an_unvalidated_result(self):
        self.assertEqual(task_result('piapi',{'status':'succeeded','output':{'data':[{'url':'https://images.example.org/image.png'}]}}),('pending',None))

    def test_piapi_retention_is_not_used_to_expire_atlascloud(self):
        with tempfile.TemporaryDirectory() as folder:
            worker=OfflineWorker(folder,'atlascloud')
            def response(url,method='GET',payload=None,headers=None,timeout=None):
                worker.calls.append((method,url,payload,headers))
                if method=='POST':
                    worker._diagnostic_context.gpt25_post_started=True
                    return {'data':{'id':'atlas_retention_1'}}
                worker._diagnostic_context.last_http_status=400
                raise RuntimeError('HTTP status=400')
            worker._request_json=response
            retention=Mock(return_value=True)
            with patch.dict(namespace,{'gpt25_result_retention_elapsed':retention}):
                with self.assertRaisesRegex(RuntimeError,'без новой оплаты'):
                    worker._gpt25_generate_image('A cup','atlascloud/gpt-image-2.5-flare')
            retention.assert_not_called()
            self.assertEqual(worker.gpt25_task_journals['atlascloud'].pending()[0].status,'poll_deferred')
            self.assertEqual([c[0] for c in worker.calls],['POST','GET'])

    def test_kling_prompt_limit_is_checked_in_contract_and_fal_payload(self):
        model='fal-ai/kling-image/o3/text-to-image'
        validate_generation_contract(model,has_references=False,ratio='1:1',resolution='1K',prompt='a'*2500)
        self.assertEqual(len(fal_generation_payload(model,'a'*2500,'1:1','1K')['prompt']),2500)
        with self.assertRaisesRegex(ValueError,'2500'):
            validate_generation_contract(model,has_references=False,ratio='1:1',resolution='1K',prompt='a'*2501)
        with self.assertRaisesRegex(ValueError,'2500'):
            fal_generation_payload(model,'a'*2501,'1:1','1K')

    def test_existing_fal_generation_profiles_keep_valid_inputs(self):
        for profile in fal_endpoint_profiles('generation'):
            spec=model_spec(profile.model_id)
            ratio=sorted(spec.ratios)[0] if spec.ratios else '1:1'
            resolution=sorted(spec.resolutions)[0] if spec.resolutions else '1K'
            with self.subTest(model=profile.model_id):
                self.assertEqual(fal_generation_payload(profile.model_id,'A ceramic cup',ratio,resolution)['prompt'],'A ceramic cup')
