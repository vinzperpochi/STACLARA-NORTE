"""Form validation classes using Flask-WTF for the Barangay Records Management System."""

from .auth import LoginForm, RegisterForm, ChangePasswordForm, ForgotPasswordForm, ResetPasswordForm
from .resident import (
    CorrectionRequestForm, DocumentRequestForm, BlotterCaseForm, QueueRequestForm,
    RequirementUploadForm
)
from .official import (
    ResidentForm, DocumentStatusForm, AdditionalRequirementForm,
    BlotterStatusForm, BlotterPartyForm, BlotterHearingForm,
    BusinessForm, WelfareForm, AssistanceForm,
    QueueUpdateForm, CollectionForm, CorrectionReviewForm
)
from .admin import (
    UserForm, RoleForm, PurokForm, DocumentTypeForm,
    FeeScheduleForm, SystemSettingsForm
)
from .common import (
    validate_phone_number, validate_email_format, validate_date_range,
    validate_file_upload, sanitize_input, ValidationError
)

__all__ = [
    # Auth forms
    'LoginForm', 'RegisterForm', 'ChangePasswordForm', 'ForgotPasswordForm', 'ResetPasswordForm',
    
    # Resident forms
    'CorrectionRequestForm', 'DocumentRequestForm', 'BlotterCaseForm', 'QueueRequestForm',
    'RequirementUploadForm',
    
    # Official forms
    'ResidentForm', 'DocumentStatusForm', 'AdditionalRequirementForm',
    'BlotterStatusForm', 'BlotterPartyForm', 'BlotterHearingForm',
    'BusinessForm', 'WelfareForm', 'AssistanceForm',
    'QueueUpdateForm', 'CollectionForm', 'CorrectionReviewForm',
    
    # Admin forms
    'UserForm', 'RoleForm', 'PurokForm', 'DocumentTypeForm',
    'FeeScheduleForm', 'SystemSettingsForm',
    
    # Validators and utilities
    'validate_phone_number', 'validate_email_format', 'validate_date_range',
    'validate_file_upload', 'sanitize_input', 'ValidationError'
]