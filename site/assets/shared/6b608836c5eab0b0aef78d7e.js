
(() => {
    const input = document.getElementById('programme-search');
    const list = document.getElementById('programme-suggestions');
    const entries = JSON.parse(document.getElementById('programme-search-data').textContent);
    const normalize = value => value.toLowerCase().replace(/\./g, '').replace(/[^\p{L}\p{N}]+/gu, ' ').trim();
    const compact = value => value.replace(/ /g, '');
    const names = entries.map(([label, target]) => ({label, target, name: normalize(label)}));
    let matches = [];
    let active = -1;

    function distance(a, b) {
        let previous = Array.from({length: b.length + 1}, (_, i) => i);
        for (let i = 1; i <= a.length; i++) {
            const row = [i];
            for (let j = 1; j <= b.length; j++) {
                row[j] = Math.min(row[j - 1] + 1, previous[j] + 1,
                    previous[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
            }
            previous = row;
        }
        return previous[b.length];
    }

    function score(query, name) {
        const key = compact(query);
        const full = compact(name);
        if (key === full) return 0;
        if (full.startsWith(key)) return 1;
        if (name.includes(query) || full.includes(key)) return 2;
        if (key.length < 3) return Infinity;
        const tolerance = key.length >= 6 ? 3 : key.length >= 4 ? 2 : 1;
        let best = Infinity;
        for (const candidate of [...name.split(' '), full]) {
            for (let size = Math.max(1, key.length - tolerance);
                 size <= Math.min(candidate.length, key.length + tolerance); size++) {
                best = Math.min(best, distance(key, candidate.slice(0, size)));
            }
        }
        return best <= tolerance ? 3 + best : Infinity;
    }

    function setOpen(open) {
        list.hidden = !open;
        input.setAttribute('aria-expanded', String(open));
        if (!open) input.removeAttribute('aria-activedescendant');
    }

    function update() {
        const query = normalize(input.value);
        active = -1;
        input.removeAttribute('aria-activedescendant');
        list.replaceChildren();
        matches = query ? names.map(entry => ({entry, rank: score(query, entry.name)}))
            .filter(item => Number.isFinite(item.rank))
            .sort((a, b) => a.rank - b.rank || a.entry.label.localeCompare(b.entry.label))
            .slice(0, 8).map(item => item.entry) : [];
        matches.forEach((entry, index) => {
            const option = document.createElement('li');
            option.id = 'programme-option-' + index;
            option.setAttribute('role', 'option');
            option.setAttribute('aria-selected', 'false');
            option.textContent = entry.label;
            option.addEventListener('pointerdown', event => event.preventDefault());
            option.addEventListener('click', () => select(index));
            list.append(option);
        });
        setOpen(matches.length > 0);
    }

    function select(index) {
        const entry = matches[index];
        if (!entry) return;
        input.value = entry.label;
        setOpen(false);
        if (input.dataset.action === 'check') {
            input.dispatchEvent(new CustomEvent('programme-selected', {detail: entry.target}));
        } else {
            window.location.assign(window.publicationLink ? window.publicationLink(entry.target) : entry.target);
        }
    }

    input.addEventListener('input', update);
    input.addEventListener('focus', update);
    input.addEventListener('blur', () => setOpen(false));
    input.addEventListener('keydown', event => {
        if (event.key === 'Escape') {
            setOpen(false);
        } else if (event.key === 'Enter' && !list.hidden) {
            event.preventDefault();
            select(Math.max(0, active));
        } else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
            if (list.hidden) update();
            if (!matches.length) return;
            event.preventDefault();
            const direction = event.key === 'ArrowDown' ? 1 : -1;
            active = active < 0 ? (direction === 1 ? 0 : matches.length - 1)
                : (active + direction + matches.length) % matches.length;
            Array.from(list.children).forEach((option, index) => {
                option.setAttribute('aria-selected', String(index === active));
            });
            input.setAttribute('aria-activedescendant', list.children[active].id);
            list.children[active].scrollIntoView({block: 'nearest'});
        }
    });
})();
