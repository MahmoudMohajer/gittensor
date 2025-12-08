document.addEventListener('DOMContentLoaded', () => {
    const searchInput = document.getElementById('search');
    let currentSort = 'updated';
    let debounceTimer;

    function fetchPRs() {
        const tbody = document.getElementById('prs-body');
        tbody.style.opacity = '0.5';

        const params = new URLSearchParams({
            search: searchInput.value,
            sort: currentSort
        });

        fetch(`/api/prs?${params}`)
            .then(response => response.json())
            .then(data => {
                const prs = data.prs;
                document.getElementById('total-prs').textContent = data.count;

                // Calculate unique authors
                const authors = [...new Set(prs.map(p => p.author))];
                document.getElementById('unique-authors').textContent = authors.length;

                // Find top competitor (most PRs)
                if (prs.length > 0) {
                    const authorCounts = {};
                    prs.forEach(p => {
                        authorCounts[p.author] = (authorCounts[p.author] || 0) + 1;
                    });
                    const topAuthor = Object.entries(authorCounts)
                        .sort((a, b) => b[1] - a[1])[0];
                    document.getElementById('top-competitor').textContent =
                        `${topAuthor[0]} (${topAuthor[1]})`;
                }

                renderTable(prs);
                tbody.style.opacity = '1';
            })
            .catch(err => {
                console.error('Error loading data:', err);
                tbody.style.opacity = '1';
            });
    }

    function debounceFetch() {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(fetchPRs, 300);
    }

    searchInput.addEventListener('input', debounceFetch);

    const filterBtns = document.querySelectorAll('.filter-btn');
    filterBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            filterBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentSort = btn.dataset.sort;
            fetchPRs();
        });
    });

    fetchPRs();
});

function renderTable(prs) {
    const tbody = document.getElementById('prs-body');
    tbody.innerHTML = '';

    prs.forEach(pr => {
        const tr = document.createElement('tr');

        const additions = pr.additions || 0;
        const deletions = pr.deletions || 0;
        const score = pr.estimated_score || 0;

        tr.innerHTML = `
            <td><div class="repo-name">${pr.repo}</div></td>
            <td><span class="weight-badge">${pr.author}</span></td>
            <td>
                <a href="${pr.url}" target="_blank" class="issue-link">#${pr.number}: ${pr.title}</a>
            </td>
            <td><span class="age-tag">+${additions}/-${deletions}</span></td>
            <td><span class="score-est">~${score.toLocaleString()}</span></td>
            <td><span class="age-tag">${pr.age} days</span></td>
            <td><a href="${pr.url}" target="_blank" class="action-btn">View</a></td>
        `;
        tbody.appendChild(tr);
    });
}
