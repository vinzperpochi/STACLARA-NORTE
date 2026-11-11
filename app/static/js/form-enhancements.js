/**
 * Form Enhancement Features
 * Adds character counting, password strength, and other UI improvements
 */

// Character Counter for Text Areas and Inputs
class CharacterCounter {
    constructor() {
        this.init();
    }
    
    init() {
        document.addEventListener('DOMContentLoaded', () => {
            this.setupCounters();
        });
    }
    
    setupCounters() {
        const fieldsWithCounters = document.querySelectorAll('[data-character-counter]');
        fieldsWithCounters.forEach(field => {
            this.addCounter(field);
        });
    }
    
    addCounter(field) {
        const maxLength = field.getAttribute('data-character-counter');
        if (!maxLength) return;
        
        // Create counter element
        const counter = document.createElement('div');
        counter.className = 'character-count';
        counter.innerHTML = `<span class="current">0</span>/<span class="max">${maxLength}</span> characters`;
        
        // Insert after field
        field.parentNode.insertBefore(counter, field.nextSibling);
        
        // Update counter on input
        const updateCounter = () => {
            const currentLength = field.value.length;
            const currentSpan = counter.querySelector('.current');
            currentSpan.textContent = currentLength;
            
            // Update styling based on length
            counter.classList.remove('warning', 'danger');
            if (currentLength > maxLength * 0.9) {
                counter.classList.add('danger');
            } else if (currentLength > maxLength * 0.8) {
                counter.classList.add('warning');
            }
        };
        
        field.addEventListener('input', updateCounter);
        updateCounter(); // Initial count
    }
}

// Password Strength Indicator
class PasswordStrength {
    constructor() {
        this.init();
    }
    
    init() {
        document.addEventListener('DOMContentLoaded', () => {
            this.setupPasswordFields();
        });
    }
    
    setupPasswordFields() {
        const passwordFields = document.querySelectorAll('input[type="password"].strong-password');
        passwordFields.forEach(field => {
            this.addStrengthIndicator(field);
        });
    }
    
    addStrengthIndicator(field) {
        // Find existing strength indicator or create one
        let strengthContainer = field.parentNode.querySelector('.password-strength');
        if (!strengthContainer) {
            strengthContainer = document.createElement('div');
            strengthContainer.className = 'password-strength';
            strengthContainer.innerHTML = '<div class="password-strength-bar"></div>';
            field.parentNode.appendChild(strengthContainer);
        }
        
        const strengthBar = strengthContainer.querySelector('.password-strength-bar');
        
        field.addEventListener('input', () => {
            const strength = this.calculateStrength(field.value);
            this.updateStrengthIndicator(strengthContainer, strengthBar, strength);
        });
    }
    
    calculateStrength(password) {
        let score = 0;
        
        if (password.length >= 8) score += 1;
        if (password.length >= 12) score += 1;
        if (/[a-z]/.test(password)) score += 1;
        if (/[A-Z]/.test(password)) score += 1;
        if (/[0-9]/.test(password)) score += 1;
        if (/[^A-Za-z0-9]/.test(password)) score += 1;
        
        // Penalty for common patterns
        if (/(.)\1{2,}/.test(password)) score -= 1; // Repeated characters
        if (/123|abc|qwe/i.test(password)) score -= 1; // Sequential patterns
        
        return Math.max(0, Math.min(score, 3));
    }
    
    updateStrengthIndicator(container, bar, strength) {
        // Remove existing classes
        container.classList.remove('password-strength-weak', 'password-strength-medium', 'password-strength-strong');
        
        // Add appropriate class
        if (strength === 0 || strength === 1) {
            container.classList.add('password-strength-weak');
        } else if (strength === 2) {
            container.classList.add('password-strength-medium');
        } else {
            container.classList.add('password-strength-strong');
        }
    }
}

// Input Formatting
class InputFormatter {
    constructor() {
        this.init();
    }
    
    init() {
        document.addEventListener('DOMContentLoaded', () => {
            this.setupFormatters();
        });
    }
    
    setupFormatters() {
        // Phone number formatting
        const phoneFields = window.civicValidation ? [] : document.querySelectorAll('input[type="tel"]');
        phoneFields.forEach(field => {
            field.addEventListener('input', this.formatPhoneNumber.bind(this));
        });
        
        // Currency formatting
        const currencyFields = document.querySelectorAll('input[data-currency]');
        currencyFields.forEach(field => {
            field.addEventListener('input', this.formatCurrency.bind(this));
            field.addEventListener('blur', this.validateCurrency.bind(this));
        });
        
        // Capitalize names
        const nameFields = document.querySelectorAll('.validate-name');
        nameFields.forEach(field => {
            field.addEventListener('blur', this.capitalizeName.bind(this));
        });
    }
    
    formatPhoneNumber(e) {
        let value = e.target.value.replace(/\D/g, '');
        
        // Philippine number formatting
        if (value.startsWith('63')) {
            value = '+' + value;
        } else if (value.startsWith('9') && value.length <= 10) {
            value = '+63' + value;
        } else if (value.startsWith('0')) {
            value = '+63' + value.substring(1);
        }
        
        e.target.value = value;
    }
    
    formatCurrency(e) {
        let value = e.target.value.replace(/[^\d.]/g, '');
        
        // Ensure only one decimal point
        const parts = value.split('.');
        if (parts.length > 2) {
            value = parts[0] + '.' + parts.slice(1).join('');
        }
        
        // Limit decimal places
        if (parts[1] && parts[1].length > 2) {
            value = parts[0] + '.' + parts[1].substring(0, 2);
        }
        
        e.target.value = value;
    }
    
    validateCurrency(e) {
        const value = parseFloat(e.target.value);
        if (!isNaN(value)) {
            e.target.value = value.toFixed(2);
        }
    }
    
    capitalizeName(e) {
        const value = e.target.value;
        const capitalized = value.toLowerCase().replace(/\b\w/g, l => l.toUpperCase());
        e.target.value = capitalized;
    }
}

// Form Auto-save (Enhanced version for specific forms)
class FormAutoSaveManager {
    constructor() {
        this.autoSavers = new Map();
        this.init();
    }
    
    init() {
        document.addEventListener('DOMContentLoaded', () => {
            this.setupAutoSave();
        });
    }
    
    setupAutoSave() {
        // Auto-save for long forms (registration, profile editing)
        const longForms = document.querySelectorAll('form[data-autosave]');
        longForms.forEach(form => {
            if (form.id) {
                const autoSaver = new FormAutoSave(form.id, {
                    interval: 15000, // 15 seconds for long forms
                    storageKey: `autosave_${form.id}_${Date.now()}`
                });
                this.autoSavers.set(form.id, autoSaver);
            }
        });
    }
    
    clearAutoSave(formId) {
        const autoSaver = this.autoSavers.get(formId);
        if (autoSaver) {
            autoSaver.clearSavedData();
        }
    }
    
    clearAllAutoSaves() {
        this.autoSavers.forEach(autoSaver => {
            autoSaver.clearSavedData();
        });
    }
}

// File Upload Enhancements
class FileUploadEnhancer {
    constructor() {
        this.init();
    }
    
    init() {
        document.addEventListener('DOMContentLoaded', () => {
            this.setupFileUploads();
        });
    }
    
    setupFileUploads() {
        const fileInputs = document.querySelectorAll('input[type="file"]');
        fileInputs.forEach(input => {
            this.enhanceFileInput(input);
        });
    }
    
    enhanceFileInput(input) {
        // Add drag and drop functionality
        const wrapper = document.createElement('div');
        wrapper.className = 'file-upload-wrapper';
        input.parentNode.insertBefore(wrapper, input);
        wrapper.appendChild(input);
        
        // Create upload area
        const uploadArea = document.createElement('div');
        uploadArea.className = 'file-upload-area';
        uploadArea.innerHTML = `
            <div class="file-upload-content">
                <svg class="icon-svg" aria-hidden="true" viewBox="0 0 16 16"><use href="/static/img/icons.svg#file-earmark"></use></svg>
                <p>Drag files here or click to select</p>
                <span class="file-upload-info">Supported formats: ${input.accept || 'All files'}</span>
            </div>
        `;
        wrapper.appendChild(uploadArea);
        
        // Hide original input
        input.style.display = 'none';
        
        // File preview area
        const previewArea = document.createElement('div');
        previewArea.className = 'file-preview-area';
        wrapper.appendChild(previewArea);
        
        // Event listeners
        uploadArea.addEventListener('click', () => input.click());
        
        uploadArea.addEventListener('dragover', (e) => {
            e.preventDefault();
            uploadArea.classList.add('dragover');
        });
        
        uploadArea.addEventListener('dragleave', () => {
            uploadArea.classList.remove('dragover');
        });
        
        uploadArea.addEventListener('drop', (e) => {
            e.preventDefault();
            uploadArea.classList.remove('dragover');
            
            const files = Array.from(e.dataTransfer.files);
            this.handleFileSelection(input, files, previewArea);
        });
        
        input.addEventListener('change', () => {
            const files = Array.from(input.files);
            this.handleFileSelection(input, files, previewArea);
        });
    }
    
    handleFileSelection(input, files, previewArea) {
        previewArea.innerHTML = '';
        
        files.forEach(file => {
            const fileItem = document.createElement('div');
            fileItem.className = 'file-preview-item';
            
            // File icon based on type
            let icon = 'bi-file-earmark';
            if (file.type.startsWith('image/')) {
                icon = 'bi-file-earmark-image';
            } else if (file.type.includes('pdf')) {
                icon = 'bi-file-earmark-pdf';
            } else if (file.type.includes('word') || file.type.includes('document')) {
                icon = 'bi-file-earmark-word';
            }
            
            fileItem.innerHTML = `
                <div class="file-preview-icon">
                    <svg class="icon-svg" aria-hidden="true" viewBox="0 0 16 16"><use href="/static/img/icons.svg#file-earmark"></use></svg>
                </div>
                <div class="file-preview-info">
                    <div class="file-name">${file.name}</div>
                    <div class="file-size">${this.formatFileSize(file.size)}</div>
                </div>
                <button type="button" class="btn-remove-file" onclick="this.parentElement.remove()">
                    <svg class="icon-svg" aria-hidden="true" viewBox="0 0 16 16"><use href="/static/img/icons.svg#x-lg"></use></svg>
                </button>
            `;
            
            previewArea.appendChild(fileItem);
        });
    }
    
    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }
}

// Form Field Dependencies
class FormDependencyManager {
    constructor() {
        this.dependencies = new Map();
        this.init();
    }
    
    init() {
        document.addEventListener('DOMContentLoaded', () => {
            this.setupDependencies();
        });
    }
    
    setupDependencies() {
        // Setup conditional field visibility
        const conditionalFields = document.querySelectorAll('[data-depends-on]');
        conditionalFields.forEach(field => {
            const dependsOn = field.getAttribute('data-depends-on');
            const dependsValue = field.getAttribute('data-depends-value');
            const controller = document.querySelector(`[name="${dependsOn}"]`);
            
            if (controller) {
                this.setupDependency(controller, field, dependsValue);
            }
        });
    }
    
    setupDependency(controller, dependent, requiredValue) {
        const checkVisibility = () => {
            const shouldShow = controller.value === requiredValue;
            dependent.style.display = shouldShow ? '' : 'none';
            
            // Clear value if hidden
            if (!shouldShow && dependent.tagName === 'INPUT') {
                dependent.value = '';
            }
        };
        
        controller.addEventListener('change', checkVisibility);
        checkVisibility(); // Initial check
    }
}

// Initialize all enhancements
const characterCounter = new CharacterCounter();
const passwordStrength = new PasswordStrength();
const inputFormatter = new InputFormatter();
const autoSaveManager = new FormAutoSaveManager();
const fileUploadEnhancer = new FileUploadEnhancer();
const dependencyManager = new FormDependencyManager();

// Export for external use
window.CharacterCounter = CharacterCounter;
window.PasswordStrength = PasswordStrength;
window.InputFormatter = InputFormatter;
window.FormAutoSaveManager = FormAutoSaveManager;
window.FileUploadEnhancer = FileUploadEnhancer;
window.FormDependencyManager = FormDependencyManager;
