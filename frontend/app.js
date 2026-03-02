document.addEventListener('DOMContentLoaded', () => {
    // Tab Switching Logic
    const tabs = document.querySelectorAll('.tab-btn');
    const contents = document.querySelectorAll('.tab-content');

    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            tabs.forEach(t => t.classList.remove('active'));
            contents.forEach(c => c.classList.remove('active'));

            tab.classList.add('active');
            document.getElementById(tab.dataset.tab).classList.add('active');
        });
    });
});

async function makeRequest(url, payload, button, outputEl) {
    const btnSpan = button.querySelector('span');
    const btnLoader = button.querySelector('.loader');
    
    // UI Loading state
    btnSpan.classList.add('hidden');
    btnLoader.classList.remove('hidden');
    button.disabled = true;
    outputEl.textContent = "Processing... this may take a moment.";
    outputEl.style.color = 'var(--text-secondary)';

    try {
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });

        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.detail || 'Unknown error occurred');
        }

        outputEl.style.color = '#a5d6ff';
        
        // Pretty print JSON response if the response looks like a json object with data vs toon string
        if (data.data) {
            outputEl.textContent = JSON.stringify(data.data, null, 2);
        } else if (data.toon) {
            outputEl.textContent = data.toon;
        } else if (data.results) {
            outputEl.textContent = JSON.stringify(data.results, null, 2);
        } else {
            outputEl.textContent = JSON.stringify(data, null, 2);
        }
    } catch (error) {
        outputEl.style.color = 'var(--error-color)';
        outputEl.textContent = `Error: ${error.message}`;
    } finally {
        btnSpan.classList.remove('hidden');
        btnLoader.classList.add('hidden');
        button.disabled = false;
    }
}

function parseResumeToJson() {
    const input = document.getElementById('resume-json-input').value;
    const btn = document.querySelector('#resume-json .primary-btn');
    const out = document.getElementById('resume-json-output');
    
    if (!input.trim()) {
        out.textContent = "Please enter some text.";
        out.style.color = 'var(--error-color)';
        return;
    }
    makeRequest('/api/parse/resume-to-json', { plaintext: input }, btn, out);
}

function parseResumeToToon() {
    const input = document.getElementById('resume-toon-input').value;
    const btn = document.querySelector('#resume-toon .primary-btn');
    const out = document.getElementById('resume-toon-output');
    
    if (!input.trim()) {
        out.textContent = "Please enter some text.";
        out.style.color = 'var(--error-color)';
        return;
    }
    makeRequest('/api/parse/resume-to-toon', { plaintext: input }, btn, out);
}

function parseJdToToon() {
    const inputStr = document.getElementById('jd-toon-input').value;
    const btn = document.querySelector('#jd-toon .primary-btn');
    const out = document.getElementById('jd-toon-output');
    
    if (!inputStr.trim()) {
        out.textContent = "Please enter some JSON.";
        out.style.color = 'var(--error-color)';
        return;
    }
    
    let payload;
    try {
        payload = JSON.parse(inputStr);
    } catch (e) {
        out.textContent = "Invalid JSON input. Please provide valid JSON array or object.";
        out.style.color = 'var(--error-color)';
        return;
    }

    makeRequest('/api/parse/jd-to-toon', payload, btn, out);
}
