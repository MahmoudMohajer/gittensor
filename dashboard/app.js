document.addEventListener('DOMContentLoaded', () => {
    let allIssues = [];

    fetch('data.json')
        .then(response => response.json())
        .then(data => {
            allIssues = data.issues;
            document.getElementById('last-updated').textContent = new Date(data.updated_at).toLocaleString();
            document.getElementById('total-issues').textContent = allIssues.length;

            if (allIssues.length > 0) {
                const maxWeight = Math.max(...allIssues.map(i => i.weight));
                document.getElementById('top-weight').textContent = maxWeight.toFixed(2);
            }

            renderTable(allIssues);
        })
        .catch(err => console.error('Error loading data:', err));

    const searchInput = document.getElementById('search');
    searchInput.addEventListener('input', (e) => {
        const term = e.target.value.toLowerCase();
        const filtered = allIssues.filter(issue =>
            issue.repo.toLowerCase().includes(term) ||
            issue.title.toLowerCase().includes(term)
        );
        renderTable(filtered);
    });

    const filterBtns = document.querySelectorAll('.filter-btn');
    filterBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            filterBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            const sortType = btn.dataset.sort;
            let sorted = [...allIssues];

            if (sortType === 'weight') {
                sorted.sort((a, b) => b.weight - a.weight);
            } else if (sortType === 'age') {
                sorted.sort((a, b) => b.age - a.age);
            }

            renderTable(sorted);
        });
    });
});

function renderTable(issues) {
    const tbody = document.getElementById('issues-body');
    tbody.innerHTML = '';

    issues.forEach(issue => {
        const tr = document.createElement('tr');

        // Calculate potential score estimate (Base 175 * Repo * Issue Bonus 3.7 * Tagline 2.0)
        // This is a rough estimate assuming 100 lines of Python
        const potentialScore = (175 * issue.weight * 3.7 * 2.0).toLocaleString(undefined, { maximumFractionDigits: 0 });

        tr.innerHTML = `
            <td><div class="repo-name">${issue.repo}</div></td>
            <td><span class="weight-badge">${issue.weight.toFixed(2)}</span></td>
            <td>
                <a href="${issue.url}" target="_blank" class="issue-link">#${issue.number}: ${issue.title}</a>
                <div style="font-size: 0.8rem; color: #666; margin-top: 4px;">by ${issue.author}</div>
            </td>
            <td><span class="age-tag">${issue.age} days</span></td>
            <td><span class="score-est">~${potentialScore}</span></td>
            <td><a href="${issue.url}" target="_blank" class="action-btn">View</a></td>
        `;
        tbody.appendChild(tr);
    });
}
