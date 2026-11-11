/**
 * Comprehensive client-side form validation system
 * Provides immediate feedback and prevents invalid submissions
 */

class FormValidator {
    constructor() {
        this.patterns = {
            email: /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/,
            phone: /^(\+63|0)?[9][0-9]{9}$|^(\+63|0)?[2-8][0-9]{7,8}$/,
            username: /^[a-zA-Z0-9_-]{3,80}$/,
            name: /^[a-zA-Z\s\-\.]{2,100}$/,
            password: /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)[A-Za-z\d@$!%*?&]{8,}$/
        };
        
        this.messages = {
            required: 'This field is required',
            email: 'Please enter a valid email address',
            phone: 'Please enter a valid Philippine phone number',
            username: 'Username must be 3-80 characters (letters, numbers, underscore, dash)',
            name: 'Name must be 2-100 characters (letters, spaces, hyphens, periods only)',
            password: 'Password must be at least 8 characters with uppercase, lowercase, and number',
            minLength: 'Minimum {min} characters required',
            maxLength: 'Maximum {max} characters allowed',
            min: 'Minimum value is {min}',
            max: 'Maximum value is {max}',
            match: 'Passwords do not match',
            date: 'Please enter a valid date',
            future: 'Date cannot be in the future',
            past: 'Date must be in the future'
        };
        
        this.init();
    }
    
    init() {
        // Initialize validation on page load
        document.addEventListener('DOMContentLoaded', () => {
            this.setupFormValidation();
            this.setupRealTimeValidation();
            this.setupCustomValidators();
        });
    }
    
    setupFormValidation() {
        const forms = document.querySelectorAll('form[novalidate]');
        forms.forEach(form => {
            // Remove novalidate to enable HTML5 validation as fallback
            form.removeAttribute('novalidate');
            
            form.addEventListener('submit', (e) => {
                if (!this.validateForm(form)) {
                    e.preventDefault();
                    e.stopPropagation();
                }
                form.classList.add('was-validated');
            });
        });
    }
    
    setupRealTimeValidation() {
        // Real-time validation on input/blur
        const inputs = document.querySelectorAll('input, select, textarea');
        inputs.forEach(input => {
            input.addEventListener('blur', () => {
                this.validateField(input);
            });
            
            input.addEventListener('input', () => {
                // Clear validation state when user starts typing
                if (input.classList.contains('is-invalid')) {
                    input.classList.remove('is-invalid');
                    this.clearFieldError(input);
                }
                
                // Validate certain fields in real-time
                if (input.type === 'email' || input.type === 'password' || 
                    input.classList.contains('validate-realtime')) {
                    this.validateField(input);
                }
            });
        });
        
        // Password confirmation validation
        const confirmPasswordFields = document.querySelectorAll('input[name="confirm_password"]');
        confirmPasswordFields.forEach(field => {
            const passwordField = field.form.querySelector('input[name="password"]');
            if (passwordField) {
                [field, passwordField].forEach(f => {
                    f.addEventListener('input', () => {
                        this.validatePasswordMatch(passwordField, field);
                    });
                });
            }
        });
    }
    
    setupCustomValidators() {
        // Phone number formatting
        const phoneFields = document.querySelectorAll('input[type="tel"]');
        phoneFields.forEach(field => {
            field.addEventListener('input', (e) => {
                let value = e.target.value.replace(/\D/g, '');
                if (value.startsWith('63')) {
                    value = '+' + value;
                } else if (value.startsWith('9') && value.length === 10) {
                    value = '+63' + value;
                } else if (value.startsWith('0')) {
                    value = '+63' + value.substring(1);
                }
                e.target.value = value;
            });
        });
        
        // Date validation
        const dateFields = document.querySelectorAll('input[type="date"]');
        dateFields.forEach(field => {
            field.addEventListener('change', () => {
                this.validateDate(field);
            });
        });
        
        // Numeric fields with ranges
        const numericFields = document.querySelectorAll('input[type="number"], input[type="range"]');
        numericFields.forEach(field => {
            field.addEventListener('input', () => {
                this.validateNumeric(field);
            });
        });
    }
    
    validateForm(form) {
        let isValid = true;
        const fields = form.querySelectorAll('input, select, textarea');
        
        fields.forEach(field => {
            if (!this.validateField(field)) {
                isValid = false;
            }
        });
        
        return isValid;
    }
    
    validateField(field) {
        if (!field.name || field.disabled) return true;
        
        let isValid = true;
        let message = '';
        
        // Check required
        if (field.hasAttribute('required') && !field.value.trim()) {
            isValid = false;
            message = this.messages.required;
        }
        
        // Skip further validation if empty and not required
        if (!field.value.trim() && !field.hasAttribute('required')) {
            this.clearFieldError(field);
            return true;
        }
        
        // Type-specific validation
        if (isValid && field.value.trim()) {
            switch (field.type) {
                case 'email':
                    if (!this.patterns.email.test(field.value)) {
                        isValid = false;
                        message = this.messages.email;
                    }
                    break;
                    
                case 'tel':
                    if (!this.patterns.phone.test(field.value)) {
                        isValid = false;
                        message = this.messages.phone;
                    }
                    break;
                    
                case 'password':
                    if (field.value.length < 8) {
                        isValid = false;
                        message = 'Password must be at least 8 characters';
                    } else if (field.classList.contains('strong-password') && 
                              !this.patterns.password.test(field.value)) {
                        isValid = false;
                        message = this.messages.password;
                    }
                    break;
                    
                case 'number':
                    if (!this.validateNumeric(field)) {
                        isValid = false;
                        message = this.getNumericErrorMessage(field);
                    }
                    break;
                    
                case 'date':
                    if (!this.validateDate(field)) {
                        isValid = false;
                        message = this.getDateErrorMessage(field);
                    }
                    break;
            }
            
            // Pattern validation
            if (isValid && field.hasAttribute('pattern')) {
                const pattern = new RegExp(field.pattern);
                if (!pattern.test(field.value)) {
                    isValid = false;
                    message = field.title || 'Invalid format';
                }
            }
            
            // Length validation
            if (isValid) {
                const minLength = field.getAttribute('minlength');
                const maxLength = field.getAttribute('maxlength');
                
                if (minLength && field.value.length < parseInt(minLength)) {
                    isValid = false;
                    message = this.messages.minLength.replace('{min}', minLength);
                }
                
                if (maxLength && field.value.length > parseInt(maxLength)) {
                    isValid = false;
                    message = this.messages.maxLength.replace('{max}', maxLength);
                }
            }
            
            // Custom validation classes
            if (isValid && field.classList.contains('validate-name')) {
                if (!this.patterns.name.test(field.value)) {
                    isValid = false;
                    message = this.messages.name;
                }
            }
            
            if (isValid && field.classList.contains('validate-username')) {
                if (!this.patterns.username.test(field.value)) {
                    isValid = false;
                    message = this.messages.username;
                }
            }
        }
        
        // Update field state
        if (isValid) {
            field.classList.remove('is-invalid');
            field.classList.add('is-valid');
            this.clearFieldError(field);
        } else {
            field.classList.remove('is-valid');
            field.classList.add('is-invalid');
            this.showFieldError(field, message);
        }
        
        return isValid;
    }
    
    validatePasswordMatch(passwordField, confirmField) {
        if (!confirmField.value) return true;
        
        const isValid = passwordField.value === confirmField.value;
        
        if (isValid) {
            confirmField.classList.remove('is-invalid');
            confirmField.classList.add('is-valid');
            this.clearFieldError(confirmField);
        } else {
            confirmField.classList.remove('is-valid');
            confirmField.classList.add('is-invalid');
            this.showFieldError(confirmField, this.messages.match);
        }
        
        return isValid;
    }
    
    validateDate(field) {
        if (!field.value) return true;
        
        const date = new Date(field.value);
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        
        let isValid = true;
        
        // Check if it's a valid date
        if (isNaN(date.getTime())) {
            isValid = false;
        }
        
        // Check future/past restrictions
        if (isValid && field.classList.contains('no-future')) {
            if (date > today) {
                isValid = false;
            }
        }
        
        if (isValid && field.classList.contains('no-past')) {
            if (date < today) {
                isValid = false;
            }
        }
        
        return isValid;
    }
    
    validateNumeric(field) {
        if (!field.value) return true;
        
        const value = parseFloat(field.value);
        const min = field.getAttribute('min');
        const max = field.getAttribute('max');
        
        let isValid = true;
        
        if (isNaN(value)) {
            isValid = false;
        }
        
        if (isValid && min !== null && value < parseFloat(min)) {
            isValid = false;
        }
        
        if (isValid && max !== null && value > parseFloat(max)) {
            isValid = false;
        }
        
        return isValid;
    }
    
    getNumericErrorMessage(field) {
        const value = parseFloat(field.value);
        const min = field.getAttribute('min');
        const max = field.getAttribute('max');
        
        if (isNaN(value)) {
            return 'Please enter a valid number';
        }
        
        if (min !== null && value < parseFloat(min)) {
            return this.messages.min.replace('{min}', min);
        }
        
        if (max !== null && value > parseFloat(max)) {
            return this.messages.max.replace('{max}', max);
        }
        
        return 'Invalid number';
    }
    
    getDateErrorMessage(field) {
        const date = new Date(field.value);
        const today = new Date();
        
        if (isNaN(date.getTime())) {
            return this.messages.date;
        }
        
        if (field.classList.contains('no-future') && date > today) {
            return this.messages.future;
        }
        
        if (field.classList.contains('no-past') && date < today) {
            return this.messages.past;
        }
        
        return 'Invalid date';
    }
    
    showFieldError(field, message) {
        // Remove existing error
        this.clearFieldError(field);
        
        // Create error element
        const errorDiv = document.createElement('div');
        errorDiv.className = 'invalid-feedback';
        errorDiv.textContent = message;
        errorDiv.id = field.name + '_error';
        
        // Insert after the field
        field.parentNode.insertBefore(errorDiv, field.nextSibling);
        
        // Set aria attributes for accessibility
        field.setAttribute('aria-invalid', 'true');
        field.setAttribute('aria-describedby', errorDiv.id);
    }
    
    clearFieldError(field) {
        const errorId = field.name + '_error';
        const existingError = document.getElementById(errorId);
        if (existingError) {
            existingError.remove();
        }
        
        field.removeAttribute('aria-invalid');
        field.removeAttribute('aria-describedby');
    }
    
    // Public methods for external use
    validateSingleField(fieldName) {
        const field = document.querySelector(`[name="${fieldName}"]`);
        if (field) {
            return this.validateField(field);
        }
        return false;
    }
    
    validateFormById(formId) {
        const form = document.getElementById(formId);
        if (form) {
            return this.validateForm(form);
        }
        return false;
    }
    
    resetFormValidation(formId) {
        const form = document.getElementById(formId);
        if (form) {
            form.classList.remove('was-validated');
            const fields = form.querySelectorAll('input, select, textarea');
            fields.forEach(field => {
                field.classList.remove('is-valid', 'is-invalid');
                this.clearFieldError(field);
            });
        }
    }
}

// Form submission handler with loading states
class FormSubmissionHandler {
    constructor() {
        this.init();
    }
    
    init() {
        document.addEventListener('DOMContentLoaded', () => {
            this.setupSubmissionHandling();
        });
    }
    
    setupSubmissionHandling() {
        const forms = document.querySelectorAll('form');
        forms.forEach(form => {
            form.addEventListener('submit', (e) => {
                const submitBtn = form.querySelector('button[type="submit"], input[type="submit"]');
                if (submitBtn) {
                    // Show loading state
                    const originalText = submitBtn.textContent;
                    submitBtn.disabled = true;
                    submitBtn.textContent = 'Processing...';
                    
                    // Add spinner if available
                    const spinner = document.createElement('span');
                    spinner.className = 'spinner-border spinner-border-sm me-2';
                    spinner.setAttribute('role', 'status');
                    submitBtn.insertBefore(spinner, submitBtn.firstChild);
                    
                    // Reset after timeout (in case of errors)
                    setTimeout(() => {
                        submitBtn.disabled = false;
                        submitBtn.textContent = originalText;
                        const existingSpinner = submitBtn.querySelector('.spinner-border');
                        if (existingSpinner) {
                            existingSpinner.remove();
                        }
                    }, 10000);
                }
            });
        });
    }
}

// Auto-save functionality for long forms
class FormAutoSave {
    constructor(formId, options = {}) {
        this.form = document.getElementById(formId);
        this.options = {
            interval: 30000, // 30 seconds
            storageKey: `form_autosave_${formId}`,
            ...options
        };
        
        if (this.form) {
            this.init();
        }
    }
    
    init() {
        this.loadSavedData();
        this.setupAutoSave();
        this.setupBeforeUnload();
    }
    
    setupAutoSave() {
        const inputs = this.form.querySelectorAll('input, select, textarea');
        inputs.forEach(input => {
            input.addEventListener('input', () => {
                clearTimeout(this.saveTimeout);
                this.saveTimeout = setTimeout(() => {
                    this.saveFormData();
                }, this.options.interval);
            });
        });
    }
    
    saveFormData() {
        const formData = new FormData(this.form);
        const data = {};
        
        for (let [key, value] of formData.entries()) {
            data[key] = value;
        }
        
        localStorage.setItem(this.options.storageKey, JSON.stringify({
            data: data,
            timestamp: Date.now()
        }));
    }
    
    loadSavedData() {
        const saved = localStorage.getItem(this.options.storageKey);
        if (saved) {
            try {
                const { data, timestamp } = JSON.parse(saved);
                
                // Check if data is not too old (24 hours)
                if (Date.now() - timestamp < 24 * 60 * 60 * 1000) {
                    // Ask user if they want to restore
                    if (confirm('Found previously saved form data. Would you like to restore it?')) {
                        Object.keys(data).forEach(key => {
                            const field = this.form.querySelector(`[name="${key}"]`);
                            if (field && !field.value) {
                                field.value = data[key];
                            }
                        });
                    }
                }
            } catch (e) {
                console.error('Failed to load saved form data:', e);
            }
        }
    }
    
    setupBeforeUnload() {
        window.addEventListener('beforeunload', (e) => {
            const hasUnsavedChanges = this.hasUnsavedChanges();
            if (hasUnsavedChanges) {
                e.preventDefault();
                e.returnValue = '';
                return '';
            }
        });
    }
    
    hasUnsavedChanges() {
        const inputs = this.form.querySelectorAll('input, select, textarea');
        return Array.from(inputs).some(input => {
            return input.value !== (input.defaultValue || '');
        });
    }
    
    clearSavedData() {
        localStorage.removeItem(this.options.storageKey);
    }
}

// Initialize everything
const formValidator = window.civicValidation || new FormValidator();
const submissionHandler = window.civicValidation ? null : new FormSubmissionHandler();

// Export for external use
window.FormValidator = FormValidator;
window.FormSubmissionHandler = FormSubmissionHandler;
window.FormAutoSave = FormAutoSave;
