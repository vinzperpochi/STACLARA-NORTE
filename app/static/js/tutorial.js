/**
 * Tutorial Mode System
 * Provides guided walkthroughs for different user roles
 * Uses Intro.js for interactive tutorials
 */

// Tutorial definitions for different pages/roles
const tutorials = {
    'resident-registration': {
        steps: [
            {
                intro: "Welcome to the Sta. Clara Norte Barangay Registration! This tutorial will guide you through the registration process."
            },
            {
                element: '#step-1',
                intro: "Step 1: Fill in your personal information including your name, birth date, and contact details."
            },
            {
                element: '#step-2',
                intro: "Step 2: Provide your residency information including your address and purok."
            },
            {
                element: '#step-3',
                intro: "Step 3: Review your information and accept the privacy notice and terms & conditions."
            },
            {
                intro: "After submitting, check your email for a verification link to complete your registration."
            }
        ]
    },
    
    'resident-dashboard': {
        steps: [
            {
                intro: "Welcome to your Resident Dashboard! Let me show you around."
            },
            {
                element: '[data-tour="navigation"]',
                intro: "Use this navigation menu to access different sections of the system.",
                position: 'right'
            },
            {
                element: '[data-tour="documents"]',
                intro: "Request barangay documents like certificates and clearances here.",
                position: 'bottom'
            },
            {
                element: '[data-tour="blotter"]',
                intro: "File incident reports or blotter cases that need barangay assistance.",
                position: 'bottom'
            },
            {
                element: '[data-tour="profile"]',
                intro: "View and update your personal information, or request corrections.",
                position: 'left'
            },
            {
                element: '[data-tour="notifications"]',
                intro: "Check your notifications for updates on your requests and important announcements.",
                position: 'left'
            },
            {
                intro: "You're all set! Click 'Done' to start using the system."
            }
        ]
    },
    
    'official-dashboard': {
        steps: [
            {
                intro: "Welcome to the Official Dashboard! Here's a quick tour of your workspace."
            },
            {
                element: '[data-tour="approvals"]',
                intro: "Review and approve pending account registrations and correction requests here.",
                position: 'bottom'
            },
            {
                element: '[data-tour="residents"]',
                intro: "Access the complete residents database with search and filter capabilities.",
                position: 'bottom'
            },
            {
                element: '[data-tour="documents"]',
                intro: "Process document requests from residents and generate certificates.",
                position: 'bottom'
            },
            {
                element: '[data-tour="blotter"]',
                intro: "Manage blotter cases and incident reports filed by residents.",
                position: 'bottom'
            },
            {
                element: '[data-tour="search"]',
                intro: "Use the global search to quickly find residents, cases, or documents.",
                position: 'bottom'
            },
            {
                intro: "That's everything! You can restart this tutorial anytime from the help menu."
            }
        ]
    },
    
    'admin-dashboard': {
        steps: [
            {
                intro: "Welcome to the Admin Dashboard! Let's explore the system administration tools."
            },
            {
                element: '[data-tour="users"]',
                intro: "Manage all user accounts, roles, and permissions from here.",
                position: 'bottom'
            },
            {
                element: '[data-tour="officials"]',
                intro: "Create and manage official accounts for barangay staff.",
                position: 'bottom'
            },
            {
                element: '[data-tour="settings"]',
                intro: "Configure system settings, puroks, document types, and other administrative options.",
                position: 'bottom'
            },
            {
                element: '[data-tour="audit"]',
                intro: "Review audit logs to track all system activities and changes.",
                position: 'left'
            },
            {
                intro: "You now have a complete overview of the admin tools. Happy managing!"
            }
        ]
    },
    
    'document-request': {
        steps: [
            {
                intro: "Let's walk through requesting a barangay document."
            },
            {
                element: '[data-tour="doc-type"]',
                intro: "First, select the type of document you need.",
                position: 'bottom'
            },
            {
                element: '[data-tour="purpose"]',
                intro: "Specify the purpose for requesting this document.",
                position: 'bottom'
            },
            {
                element: '[data-tour="requirements"]',
                intro: "Upload any required supporting documents if applicable.",
                position: 'bottom'
            },
            {
                intro: "After submitting, you can track your request status from your dashboard."
            }
        ]
    }
};

// Initialize tutorial system
function initializeTutorial() {
    // Check if Intro.js is loaded
    if (typeof introJs === 'undefined') {
        console.warn('Intro.js not loaded. Tutorial mode unavailable.');
        return;
    }
    
    // Add tutorial trigger buttons
    addTutorialTriggers();
    
    // Auto-start tutorial for first-time users (stored in localStorage)
    checkFirstTimeUser();
}

function addTutorialTriggers() {
    // Find tutorial start buttons
    const tutorialButtons = document.querySelectorAll('[data-start-tutorial]');
    
    tutorialButtons.forEach(button => {
        button.addEventListener('click', function() {
            const tutorialName = this.dataset.startTutorial;
            startTutorial(tutorialName);
        });
    });
}

function startTutorial(tutorialName) {
    const tutorial = tutorials[tutorialName];
    
    if (!tutorial) {
        console.error(`Tutorial "${tutorialName}" not found`);
        return;
    }
    
    const intro = introJs();
    
    intro.setOptions({
        steps: tutorial.steps,
        showProgress: true,
        showBullets: false,
        exitOnOverlayClick: false,
        dontShowAgain: true,
        dontShowAgainLabel: "Don't show again",
        nextLabel: 'Next →',
        prevLabel: '← Back',
        doneLabel: 'Done',
        skipLabel: 'Skip Tutorial'
    });
    
    // Save completion status
    intro.oncomplete(function() {
        markTutorialCompleted(tutorialName);
    });
    
    intro.onexit(function() {
        // User skipped or closed tutorial
        console.log(`Tutorial ${tutorialName} exited`);
    });
    
    intro.start();
}

function checkFirstTimeUser() {
    // Get current page tutorial name from body data attribute
    const tutorialName = document.body.dataset.tutorial;
    
    if (!tutorialName) {
        return; // No tutorial for this page
    }
    
    const completedKey = `tutorial_completed_${tutorialName}`;
    const hasCompleted = localStorage.getItem(completedKey);
    
    // Auto-start if first time
    if (!hasCompleted) {
        // Delay slightly to let page fully load
        setTimeout(() => {
            startTutorial(tutorialName);
        }, 1000);
    }
}

function markTutorialCompleted(tutorialName) {
    const completedKey = `tutorial_completed_${tutorialName}`;
    localStorage.setItem(completedKey, 'true');
}

function resetTutorial(tutorialName) {
    const completedKey = `tutorial_completed_${tutorialName}`;
    localStorage.removeItem(completedKey);
}

function resetAllTutorials() {
    Object.keys(tutorials).forEach(tutorialName => {
        resetTutorial(tutorialName);
    });
    alert('All tutorials have been reset. They will show again on your next visit.');
}

// Add help menu tutorial triggers
function addHelpMenuTutorials() {
    const helpMenu = document.querySelector('[data-help-menu]');
    
    if (!helpMenu) {
        return;
    }
    
    // Add tutorial restart option to help menu
    const tutorialOption = document.createElement('button');
    tutorialOption.className = 'block w-full text-left px-4 py-2 text-sm text-gray-700 hover:bg-gray-100';
    tutorialOption.textContent = '🎓 Restart Tutorial';
    tutorialOption.onclick = function() {
        const tutorialName = document.body.dataset.tutorial;
        if (tutorialName) {
            resetTutorial(tutorialName);
            startTutorial(tutorialName);
        }
    };
    
    helpMenu.appendChild(tutorialOption);
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    initializeTutorial();
    addHelpMenuTutorials();
});

// Expose functions globally for manual triggering
window.startTutorial = startTutorial;
window.resetTutorial = resetTutorial;
window.resetAllTutorials = resetAllTutorials;
