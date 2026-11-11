/**
 * Table sorting functionality
 * Adds sorting capability to data tables with sortable column headers
 */

document.addEventListener('DOMContentLoaded', function() {
    initializeSortableHeaders();
});

function initializeSortableHeaders() {
    const sortableHeaders = document.querySelectorAll('[data-sortable]');
    
    sortableHeaders.forEach(header => {
        header.style.cursor = 'pointer';
        header.classList.add('sortable-header');
        
        // Add sort indicator if not present
        if (!header.querySelector('.sort-indicator')) {
            const indicator = document.createElement('span');
            indicator.className = 'sort-indicator ml-1';
            indicator.innerHTML = '↕';
            header.appendChild(indicator);
        }
        
        header.addEventListener('click', function() {
            const column = this.dataset.sortable;
            sortTable(column);
        });
    });
    
    // Highlight current sort column
    const urlParams = new URLSearchParams(window.location.search);
    const currentSort = urlParams.get('sort');
    const currentOrder = urlParams.get('order') || 'asc';
    
    if (currentSort) {
        const activeHeader = document.querySelector(`[data-sortable="${currentSort}"]`);
        if (activeHeader) {
            activeHeader.classList.add('sort-active');
            const indicator = activeHeader.querySelector('.sort-indicator');
            if (indicator) {
                indicator.innerHTML = currentOrder === 'asc' ? '↑' : '↓';
            }
        }
    }
}

function sortTable(column) {
    const urlParams = new URLSearchParams(window.location.search);
    const currentSort = urlParams.get('sort');
    const currentOrder = urlParams.get('order') || 'asc';
    
    // Toggle order if clicking same column, otherwise default to asc
    let newOrder = 'asc';
    if (currentSort === column && currentOrder === 'asc') {
        newOrder = 'desc';
    }
    
    // Update URL parameters
    urlParams.set('sort', column);
    urlParams.set('order', newOrder);
    urlParams.delete('page'); // Reset to first page when sorting
    
    // Navigate to new URL
    window.location.search = urlParams.toString();
}

// Add CSS styles dynamically
const style = document.createElement('style');
style.textContent = `
    .sortable-header {
        user-select: none;
        transition: background-color 0.2s;
    }
    
    .sortable-header:hover {
        background-color: rgba(0, 0, 0, 0.05);
    }
    
    .sort-active {
        font-weight: 600;
        color: #047857;
    }
    
    .sort-indicator {
        display: inline-block;
        opacity: 0.5;
        font-size: 0.875rem;
    }
    
    .sort-active .sort-indicator {
        opacity: 1;
        color: #047857;
    }
`;
document.head.appendChild(style);
