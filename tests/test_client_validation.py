"""Existing backend constraints are exposed to browser forms without relaxing them."""
import json
from html.parser import HTMLParser
from app.forms.official import ResidentForm, CollectionForm
from app.forms.auth import RegisterForm, ChangePasswordForm
from app.forms.common import client_validation_schema
from test_system_integrity import system, login


def test_resident_rule_metadata_covers_phone_dates_names_and_files(system):
    form=ResidentForm()
    schema=client_validation_schema(form)['fields']
    assert schema['first_name']['data-validate-name']=='true'
    assert 'pattern' not in schema['first_name']
    assert schema['first_name']['minlength']==2
    assert schema['contact_number']['type']=='tel'
    assert schema['birth_date']['min']=='1900-01-01' and schema['birth_date']['max']
    assert schema['proof_of_residency']['data-allowed-extensions']=='jpg,jpeg,png'
    assert schema['proof_of_residency']['data-max-file-bytes']==5*1024*1024
    assert schema['emergency_contact_number']['data-required-with']=='emergency_contact_name'


def test_registration_uses_required_file_and_age_constraints(system):
    system.config['REGISTRATION_REQUIRE_COMPLETE_PROFILE']=True
    form=RegisterForm()
    schema=client_validation_schema(form)['fields']
    assert schema['proof_of_residency']['required'] is True
    assert schema['privacy_consent']['required'] is True
    assert schema['birth_date']['max'][:4] < '2026'
    assert schema['special_categories']['data-min-age']=='60'


def test_money_and_password_rules_keep_configured_values(system):
    amount=client_validation_schema(CollectionForm())['fields']['amount']
    assert amount['min']==0.01 and amount['max']==100000 and amount['step']=='0.01'
    assert amount['type']=='number'
    system.config['PASSWORD_MIN_LENGTH']=14
    password=client_validation_schema(ChangePasswordForm())['fields']
    assert password['new_password']['minlength']==14
    assert password['new_password']['data-password-policy']=='complex'
    assert password['password_confirmation']['data-equal-to']=='new_password'
    assert 'minlength' not in password['current_password']


def test_shared_assets_and_metadata_render_in_each_shell(system):
    pages=[(None,'/auth/login'),('admin-test','/admin/users'),('staff-test','/official/residents/new'),('resident-test','/resident/profile-details')]
    for account,path in pages:
        client=login(system,account) if account else system.test_client()
        response=client.get(path)
        assert response.status_code==200
        source=response.get_data(as_text=True)
        assert source.count('js/client-validation.js')==1
        assert 'css/client-validation.css' in source
        assert 'data-client-validation-schema' in source


def test_manual_correction_template_gets_backend_length_and_type_rules(system):
    source=login(system).get('/resident/correction-requests').get_data(as_text=True)
    assert 'data-correction-value' in source and 'data-correction-date-min' in source
    # The embedded schema is safe JSON, not a script assembled from user text.
    class Schema(HTMLParser):
        def __init__(self): super().__init__();self.active=False;self.contents=''
        def handle_starttag(self,tag,attrs): self.active=tag=='script' and 'data-client-validation-schema' in dict(attrs)
        def handle_data(self,data):
            if self.active:self.contents+=data
    parser=Schema();parser.feed(source)
    schema=json.loads(parser.contents)['fields']
    assert schema['reason']['minlength']==10 and schema['reason']['maxlength']==500
    assert schema['proposed_value']['maxlength']==255
