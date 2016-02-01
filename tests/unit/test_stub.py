# Copyright 2016 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"). You
# may not use this file except in compliance with the License. A copy of
# the License is located at
#
# http://aws.amazon.com/apache2.0/
#
# or in the "license" file accompanying this file. This file is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF
# ANY KIND, either express or implied. See the License for the specific
# language governing permissions and limitations under the License.

from tests import unittest
import mock

from botocore.stub import Stubber
from botocore.exceptions import ParamValidationError, StubResponseError
from botocore.model import ServiceModel
from botocore import hooks


class TestStubber(unittest.TestCase):
    def setUp(self):
        self.event_emitter = hooks.HierarchicalEmitter()
        self.client = mock.Mock()
        self.client.meta.events = self.event_emitter
        self.client.meta.method_to_api_mapping.get.return_value = 'foo'
        self.stubber = Stubber(self.client)
        self.validate_parameters_mock = mock.Mock()
        self.validate_parameters_patch = mock.patch(
            'botocore.stub.validate_parameters', self.validate_parameters_mock)
        self.validate_parameters_patch.start()

    def tearDown(self):
        self.validate_parameters_patch.stop()

    def emit_get_response_event(self, model=None, request_dict=None,
                                signer=None, context=None):
        if model is None:
            model = mock.Mock()
            model.name = 'foo'

        handler, response = self.event_emitter.emit_until_response(
            event_name='before-call.myservice.foo', model=model,
            params=request_dict, request_signer=signer, context=context)

        return response

    def test_stubber_registers_events(self):
        self.event_emitter = mock.Mock()
        self.client.meta.events = self.event_emitter
        self.stubber.activate()
        self.assertTrue(self.event_emitter.register.called)

    def test_stubber_unregisters_events(self):
        self.event_emitter = mock.Mock()
        self.client.meta.events = self.event_emitter
        self.stubber.activate()
        self.stubber.deactivate()
        self.assertTrue(self.event_emitter.unregister.called)

    def test_add_response(self):
        response = {'foo': 'bar'}
        self.stubber.add_response('foo', response)

        with self.assertRaises(AssertionError):
            self.stubber.assert_no_pending_responses()

    def test_add_response_fails_when_missing_client_method(self):
        del self.client.foo
        with self.assertRaises(ValueError):
            self.stubber.add_response('foo', {})

    def test_validates_service_response(self):
        self.stubber.add_response('foo', {})
        self.assertTrue(self.validate_parameters_mock.called)

    def test_validate_ignores_response_metadata(self):
        service_response = {'ResponseMetadata': {'foo': 'bar'}}
        service_model = ServiceModel({
            'documentation': '',
            'operations': {
                'foo': {
                    'name': 'foo',
                    'input': {'shape': 'StringShape'},
                    'output': {'shape': 'StringShape'}
                }
            },
            'shapes': {
                'StringShape': {'type': 'string'}
            }
        })
        op_name = service_model.operation_names[0]
        output_shape = service_model.operation_model(op_name).output_shape

        self.client.meta.service_model = service_model
        self.stubber.add_response('TestOperation', service_response)
        self.validate_parameters_mock.assert_called_with(
            {}, output_shape)

        # Make sure service response hasn't been mutated
        self.assertEqual(service_response, {'ResponseMetadata': {'foo': 'bar'}})

    def test_validates_on_empty_output_shape(self):
        service_model = ServiceModel({
            'documentation': '',
            'operations': {
                'foo': {
                    'name': 'foo'
                }
            }
        })
        self.client.meta.service_model = service_model

        with self.assertRaises(ParamValidationError):
            self.stubber.add_response('TestOperation', {'foo': 'bar'})

    def test_get_response(self):
        service_response = {'bar': 'baz'}
        self.stubber.add_response('foo', service_response)
        self.stubber.activate()
        response = self.emit_get_response_event()
        self.assertEqual(response[1], service_response)
        self.assertEqual(response[0].status_code, 200)

    def test_get_client_error_response(self):
        error_code = "foo"
        service_message = "bar"
        self.stubber.add_client_error('foo', error_code, service_message)
        self.stubber.activate()
        response = self.emit_get_response_event()
        self.assertEqual(response[1]['Error']['Message'], service_message)
        self.assertEqual(response[1]['Error']['Code'], error_code)

    def test_get_response_errors_with_no_stubs(self):
        self.stubber.activate()
        with self.assertRaises(StubResponseError):
            self.emit_get_response_event()

    def test_assert_no_responses_remaining(self):
        self.stubber.add_response('foo', {})
        with self.assertRaises(AssertionError):
            self.stubber.assert_no_pending_responses()