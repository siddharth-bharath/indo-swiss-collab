// --- GLOBAL HELPER FUNCTIONS ---

// Called from pagination buttons in results.html
window.changePage = function (page) {
    const form = document.getElementById('searchForm');
    if (!form) return;
    let pageInput = form.querySelector('input[name="page"]');
    if (!pageInput) {
        pageInput = document.createElement('input');
        pageInput.type = 'hidden';
        pageInput.name = 'page';
        form.appendChild(pageInput);
    }
    pageInput.value = page;
    form.submit();
};


// --- SCRIPT INITIALIZATION ---

document.addEventListener('DOMContentLoaded', function () {
    
    // Initialize all Bootstrap tooltips with a shorter delay
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl, {
            delay: { "show": 50, "hide": 100 }
        });
    });

    // --- INDEX PAGE LOGIC ---
    const indexPageContainer = document.querySelector('.search-container');
    if (indexPageContainer) {
        
        // Autocomplete for authors and institutions
        function setupAutocomplete(inputName, endpoint, datalistId) {
            const input = document.querySelector(`input[name="${inputName}"]`);
            if (input) {
                let datalist = document.getElementById(datalistId);
                if (!datalist) {
                    datalist = document.createElement('datalist');
                    datalist.id = datalistId;
                    document.body.appendChild(datalist);
                }
                input.setAttribute('list', datalistId);

                fetch(endpoint)
                    .then(res => res.json())
                    .then(data => {
                        const items = endpoint.includes('authors') ? data.authors : data.institutions;
                        const fragment = document.createDocumentFragment();
                        items.forEach(item => {
                            const option = document.createElement('option');
                            option.value = item;
                            fragment.appendChild(option);
                        });
                        datalist.appendChild(fragment);
                    });
            }
        }
        setupAutocomplete('authors', '/authors', 'authorsList');
        setupAutocomplete('affiliations', '/institutions', 'institutionList');

        // Dynamic multi-input support for authors/institutions
        function attachAddButtonListener(btn) {
            btn.addEventListener('click', () => {
                const container = document.getElementById(btn.dataset.target);
                const lastInput = container.querySelector('.multi-input:last-of-type');
                const clone = lastInput.cloneNode(true);
                clone.querySelector('input').value = '';
                
                const newAddBtn = clone.querySelector('.add-btn');
                attachAddButtonListener(newAddBtn);
                
                container.appendChild(clone);
            });
        }
        document.querySelectorAll('.add-btn').forEach(btn => {
            attachAddButtonListener(btn);
        });
    }


    // --- RESULTS PAGE LOGIC ---
    const resultsPageContainer = document.querySelector('.results-table');
    if (resultsPageContainer) {

        // Client-side filter for the current page of results
        const filterInput = document.getElementById('tableSearch');
        if (filterInput) {
            filterInput.addEventListener('input', function () {
                const filterValue = this.value.toLowerCase();
                const rows = document.querySelectorAll('.table-row');
                let visibleCount = 0;
                rows.forEach(row => {
                    if (row.textContent.toLowerCase().includes(filterValue)) {
                        row.style.display = '';
                        visibleCount++;
                    } else {
                        row.style.display = 'none';
                    }
                });
                // Update the count badge
                const countBadge = document.querySelector('.count-badge');
                if(countBadge) {
                    const originalTotal = countBadge.textContent.split('out of ')[1] || '...';
                    countBadge.textContent = `Showing ${visibleCount} results out of ${originalTotal}`;
                }
            });
        }
        
        // Download button loading state
        const downloadBtn = document.querySelector('.download-btn');
        if (downloadBtn) {
          downloadBtn.addEventListener('click', function (e) {
            e.preventDefault();
            const form = this.closest('form');
            this.innerHTML = `<i class="fas fa-spinner fa-spin me-2"></i>Downloading...`;
            this.disabled = true;
            form.submit();
          });
        }
    }

    // Expand/collapse long text in table (Used on Results Page)
    document.addEventListener('click', function(event) {
        const expandButton = event.target.closest('.expand-btn');
        if (!expandButton) return;

        const cell = expandButton.closest('.expandable-cell');
        const preview = cell.querySelector('.text-preview');
        const full = cell.querySelector('.text-full');
        const icon = expandButton.querySelector('.expand-icon');
        const isExpanded = cell.classList.toggle('expanded');

        preview.style.display = isExpanded ? 'none' : 'inline';
        full.style.display = isExpanded ? 'inline' : 'none';
        icon.classList.toggle('fa-chevron-down', !isExpanded);
        icon.classList.toggle('fa-chevron-up', isExpanded);
        expandButton.setAttribute('title', isExpanded ? 'Show less' : 'Show full text');
    });

    // --- UNIVERSAL WIDGETS ---

    // Scroll-to-top button
    function initializeScrollToTop() {
        if (document.querySelector('.scroll-to-top')) return; // Already initialized
        
        let btn = document.createElement('button');
        btn.innerHTML = '↑';
        btn.className = 'scroll-to-top';
        btn.title = 'Go to top';
        btn.style.cssText = `
            position: fixed; bottom: 20px; right: 20px; background: #b45252; color: white;
            border: none; border-radius: 50%; width: 50px; height: 50px; font-size: 20px;
            cursor: pointer; opacity: 0; transition: all 0.3s ease; z-index: 1000;
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.2); pointer-events: none;
        `;
        document.body.appendChild(btn);

        window.addEventListener('scroll', () => {
            if (window.pageYOffset > 300) {
                btn.style.opacity = '1';
                btn.style.pointerEvents = 'auto';
            } else {
                btn.style.opacity = '0';
                btn.style.pointerEvents = 'none';
            }
        });
        btn.addEventListener('click', () => window.scrollTo({ top: 0, behavior: 'smooth' }));
        btn.addEventListener('mouseenter', () => { btn.style.background = '#9d2828'; btn.style.transform = 'scale(1.1)'; });
        btn.addEventListener('mouseleave', () => { btn.style.background = '#b45252'; btn.style.transform = 'scale(1)'; });
    }
    initializeScrollToTop();

});