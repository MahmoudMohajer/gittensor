document.addEventListener('DOMContentLoaded', () => {
    const searchInput = document.getElementById('search');
    const minAgeInput = document.getElementById('min-age');
    const maxAgeInput = document.getElementById('max-age');
    let currentSort = 'weight';
    let debounceTimer;

    function fetchIssues() {
        // Show loading state if needed
        const tbody = document.getElementById('issues-body');
        tbody.style.opacity = '0.5';

        const params = new URLSearchParams({
            search: searchInput.value,
            min_age: minAgeInput.value || 0,
            max_age: maxAgeInput.value || 99999,
            sort: currentSort
        });

        fetch(`/api/issues?${params}`)
            .then(response => response.json())
            .then(data => {
                const issues = data.issues;
                document.getElementById('total-issues').textContent = data.count;
                document.getElementById('last-updated').textContent = 'Live'; // Or api could return DB time

                if (issues.length > 0) {
                    const maxWeight = Math.max(...issues.map(i => i.weight));
                    document.getElementById('top-weight').textContent = maxWeight.toFixed(2);

                    const easyCount = issues.filter(i => i.difficulty === 'Easy').length;
                    document.getElementById('easy-issues').textContent = easyCount;
                } else {
                    document.getElementById('top-weight').textContent = '0';
                    document.getElementById('easy-issues').textContent = '0';
                }

                renderTable(issues);
                tbody.style.opacity = '1';
            })
            .catch(err => {
                console.error('Error loading data:', err);
                tbody.style.opacity = '1';
            });
    }

    // Debounce function to prevent API spam
    function debounceFetch() {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(fetchIssues, 300);
    }

    searchInput.addEventListener('input', debounceFetch);
    minAgeInput.addEventListener('input', debounceFetch);
    maxAgeInput.addEventListener('input', debounceFetch);

    const filterBtns = document.querySelectorAll('.filter-btn');
    filterBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            filterBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            currentSort = btn.dataset.sort;
            fetchIssues();
        });
    });

    // Initial load
    fetchIssues();
});

function renderTable(issues) {
    const tbody = document.getElementById('issues-body');
    tbody.innerHTML = '';

    issues.forEach(issue => {
        const tr = document.createElement('tr');

        // Calculate potential score estimate (Base 175 * Repo * Issue Bonus 3.7 * Tagline 2.0)
        // This is a rough estimate assuming 100 lines of Python
        const potentialScore = (175 * issue.weight * 3.7 * 2.0).toLocaleString(undefined, { maximumFractionDigits: 0 });

        const diffClass = `badge-${(issue.difficulty || 'Medium').toLowerCase()}`;

        tr.innerHTML = `
            <td><div class="repo-name">${issue.repo}</div></td>
            <td><span class="weight-badge">${issue.weight.toFixed(2)}</span></td>
            <td>
                <a href="${issue.url}" target="_blank" class="issue-link">#${issue.number}: ${issue.title}</a>
                <div style="font-size: 0.8rem; color: #666; margin-top: 4px;">by ${issue.author}</div>
            </td>
             <td><span class="${diffClass}">${issue.difficulty || 'Medium'}</span></td>
            <td><span class="age-tag">${issue.age} days</span></td>
            <td><span class="score-est">~${potentialScore}</span></td>
            <td><a href="${issue.url}" target="_blank" class="action-btn">View</a></td>
        `;
        tbody.appendChild(tr);
    });
}
