/* ============================================================================
   LLMWikiNG – Syntax Highlighter (Native ES-Module)
   Copyright (C) 2026 ZeroDot1 — AGPL v3

   Client-side fallback highlighter. The server already produces Pygments/
   `codehilite` HTML for fenced code blocks (see backend/services/markdown.py),
   which is styled via the `.codehilite` rules in tailwind-build.css. This
   module only steps in for code blocks that were NOT pre-highlighted by the
   server (e.g. editor preview, dynamically injected content) and applies the
   same token classes so the CSS colours them consistently.

   It assigns functions to `window` for backward compatibility with classic
   script consumers (e.g. prompt_editor.html).
   ========================================================================== */

const rxStrings = /"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`/g;
const rxNumbers = /\b\d+(\.\d+)?\b/g;

const languages = {
    python: [
        { type: 'comment', regex: /#.*/g },
        { type: 'string', regex: rxStrings },
        { type: 'keyword', regex: /\b(def|class|return|if|elif|else|for|while|break|continue|try|except|finally|with|as|lambda|pass|import|from|in|is|not|and|or|True|False|None|self|nonlocal|global|yield|await|async|assert|print)\b/g },
        { type: 'number', regex: rxNumbers },
        { type: 'function', regex: /\b[a-zA-Z_]\w*(?=\()/g },
        { type: 'decorator', regex: /@[a-zA-Z_]\w*/g }
    ],
    py: 'python',
    javascript: [
        { type: 'comment', regex: /\/\/.*|\/\*[\s\S]*?\*\//g },
        { type: 'string', regex: rxStrings },
        { type: 'keyword', regex: /\b(const|let|var|function|return|if|else|for|while|do|break|continue|switch|case|default|class|constructor|extends|super|import|export|from|as|new|this|typeof|instanceof|void|yield|await|async|true|false|null|undefined|static|get|set|try|catch|finally|throw)\b/g },
        { type: 'number', regex: rxNumbers },
        { type: 'function', regex: /\b[a-zA-Z_]\w*(?=\()/g }
    ],
    js: 'javascript',
    typescript: 'javascript',
    ts: 'javascript',
    html: [
        { type: 'comment', regex: /<!--[\s\S]*?-->/g },
        { type: 'string', regex: rxStrings },
        { type: 'tag', regex: /<\/?[a-zA-Z0-9\-]+(?:>|\s)?/g },
        { type: 'attribute', regex: /\s[a-zA-Z0-9\-]+(?=\s*=)/g }
    ],
    xml: 'html',
    css: [
        { type: 'comment', regex: /\/\*[\s\S]*?\*\//g },
        { type: 'string', regex: rxStrings },
        { type: 'selector', regex: /([a-zA-Z0-9\-\.\#\:\,\s\+\[\]\=\"\']+)(?=\s*\{)/g },
        { type: 'property', regex: /[a-zA-Z\-]+(?=\s*\:)/g },
        { type: 'value', regex: /(?<=\:\s*)([^\;\}]+)/g }
    ],
    json: [
        { type: 'string', regex: rxStrings },
        { type: 'number', regex: rxNumbers },
        { type: 'keyword', regex: /\b(true|false|null)\b/g },
        { type: 'property', regex: /"(?:\\.|[^"\\])*"(?=\s*\:)/g }
    ],
    bash: [
        { type: 'comment', regex: /#.*/g },
        { type: 'string', regex: rxStrings },
        { type: 'keyword', regex: /\b(if|then|else|elif|fi|case|esac|for|while|in|do|done|exit|return|function|echo|local|export|alias|sudo)\b/g },
        { type: 'number', regex: rxNumbers }
    ],
    sh: 'bash',
    shell: 'bash',
    rust: [
        { type: 'comment', regex: /\/\/.*|\/\*[\s\S]*?\*\//g },
        { type: 'string', regex: rxStrings },
        { type: 'keyword', regex: /\b(fn|let|mut|match|if|else|loop|while|for|in|return|break|continue|struct|enum|impl|trait|use|pub|mod|crate|self|Self|static|const|unsafe|extern|async|await|type|as|where|true|false)\b/g },
        { type: 'number', regex: rxNumbers },
        { type: 'decorator', regex: /\b[a-zA-Z_]\w*\!/g }
    ],
    rs: 'rust',
    cpp: [
        { type: 'comment', regex: /\/\/.*|\/\*[\s\S]*?\*\//g },
        { type: 'string', regex: rxStrings },
        { type: 'keyword', regex: /\b(int|float|double|char|void|bool|if|else|for|while|do|switch|case|default|break|continue|return|class|struct|union|enum|public|private|protected|virtual|override|inline|constexpr|const|static|extern|template|typename|namespace|using|new|delete|try|catch|throw|true|false|NULL)\b/g },
        { type: 'number', regex: rxNumbers },
        { type: 'decorator', regex: /#(include|define|ifdef|ifndef|endif|pragma|if|else|elif)\b.*/g }
    ],
    'c++': 'cpp', 'c+': 'cpp', c: 'cpp', h: 'cpp', hpp: 'cpp',
    php: [
        { type: 'comment', regex: /\/\/.*|\/\*[\s\S]*?\*\/|#.*/g },
        { type: 'string', regex: rxStrings },
        { type: 'keyword', regex: /\b(echo|print|class|function|public|private|protected|static|return|if|else|elseif|foreach|for|while|do|switch|case|break|continue|try|catch|finally|throw|new|clone|global|namespace|use|extends|implements|trait|array|list|empty|isset|true|false|null)\b/g },
        { type: 'decorator', regex: /\$[a-zA-Z_]\w*/g },
        { type: 'number', regex: rxNumbers }
    ],
    sql: [
        { type: 'comment', regex: /--.*|\/\*[\s\S]*?\*\//g },
        { type: 'string', regex: rxStrings },
        { type: 'keyword', regex: /\b(SELECT|FROM|WHERE|INSERT|INTO|UPDATE|SET|DELETE|CREATE|TABLE|DROP|ALTER|ADD|INDEX|JOIN|INNER|LEFT|RIGHT|FULL|ON|GROUP|BY|ORDER|HAVING|LIMIT|UNION|ALL|AND|OR|NOT|IN|LIKE|BETWEEN|IS|NULL|TRUE|FALSE)\b/gi },
        { type: 'number', regex: rxNumbers }
    ]
};

const GENERIC_RULES = [
    { type: 'comment', regex: /(\/\/.*|\/\*[\s\S]*?\*\/|#.*)/g },
    { type: 'string', regex: rxStrings },
    { type: 'keyword', regex: /\b(class|def|function|return|if|else|elif|for|while|break|continue|import|export|from|const|let|var|true|false|null|None|public|private|static|new|try|catch|throw)\b/g },
    { type: 'number', regex: rxNumbers }
];

export function highlightCode(code, lang) {
    if (!code) return "";
    lang = (lang || "").toLowerCase().trim();

    let rules = languages[lang] || [];
    if (typeof rules === 'string') rules = languages[rules] || [];
    if (rules.length === 0) rules = GENERIC_RULES;

    const escape = (str) => str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

    // Collect all matches
    let matches = [];
    rules.forEach(rule => {
        let rx = rule.regex;
        if (!rx.global) rx = new RegExp(rx.source, rx.flags + 'g');
        rx.lastIndex = 0;
        let match;
        while ((match = rx.exec(code)) !== null) {
            if (match[0].length === 0) { rx.lastIndex++; continue; }
            matches.push({
                type: rule.type,
                start: match.index,
                end: match.index + match[0].length,
                text: match[0]
            });
        }
    });

    // Sort by start ascending, then by length descending (longer wins on ties)
    matches.sort((a, b) => {
        if (a.start !== b.start) return a.start - b.start;
        return (b.end - b.start) - (a.end - a.start);
    });

    // Resolve overlaps (keep first non-overlapping)
    let nonOverlapping = [];
    let lastEnd = 0;
    for (let m of matches) {
        if (m.start >= lastEnd) {
            nonOverlapping.push(m);
            lastEnd = m.end;
        }
    }

    // Build HTML
    let result = [];
    let currentIdx = 0;
    for (let m of nonOverlapping) {
        if (m.start > currentIdx) {
            result.push(escape(code.substring(currentIdx, m.start)));
        }
        result.push(`<span class="hl-${m.type}">${escape(m.text)}</span>`);
        currentIdx = m.end;
    }
    if (currentIdx < code.length) {
        result.push(escape(code.substring(currentIdx)));
    }

    return result.join('');
}

/**
 * Highlight all <pre><code> (and bare <pre>) blocks that were NOT already
 * highlighted by the server (no `.codehilite` ancestor and no `.hl-*` spans
 * inside). This is the fallback path for editor previews and dynamically
 * injected content.
 */
export function highlightAllPending(root = document) {
    const blocks = root.querySelectorAll('pre > code, pre code, pre:not(:has(code))');
    blocks.forEach(codeEl => {
        const pre = codeEl.closest('pre');
        // Skip blocks already processed by the server (codehilite) or by us
        if (codeEl.classList.contains('hl-processed') || (pre && (pre.classList.contains('codehilite') || pre.classList.contains('hl-processed')))) {
            return;
        }
        
        // Mark as processed immediately to prevent recursive loops
        codeEl.classList.add('hl-processed');
        if (pre) {
            pre.classList.add('hl-processed');
        }

        // Determine language from class="language-xxx" or class="xxx"
        let lang = '';
        const cls = (codeEl.className || '');
        const m = cls.match(/language-([\w+#]+)/) || cls.match(/^([\w+#]+)$/);
        if (m) lang = m[1];
        const rawText = codeEl.textContent;
        if (!rawText.trim()) return;
        codeEl.innerHTML = highlightCode(rawText, lang);
    });
}

// Backward compatibility for classic-script consumers
window.highlightCode = highlightCode;
window.highlightAllPending = highlightAllPending;

// Run automatically. Module scripts are deferred, so the DOM is ready, but we
// also observe dynamically injected content (e.g. SPA-like navigation,
// editor preview, search results).
function init() {
    // Respect the global setting from config.json (window.SYNTAX_HIGHLIGHTING).
    // When disabled, we leave code blocks untouched.
    if (window.SYNTAX_HIGHLIGHTING === false) return;
    highlightAllPending(document);
    if ('MutationObserver' in window) {
        const observer = new MutationObserver((mutations) => {
            let shouldRun = false;
            for (const mut of mutations) {
                let hasExternalAdd = false;
                mut.addedNodes.forEach(node => {
                    if (node.nodeType === Node.ELEMENT_NODE) {
                        if (!node.classList.contains('hl-processed') && !node.classList.contains('hl-keyword') && !node.classList.contains('hl-string') && !node.classList.contains('hl-comment') && !node.classList.contains('hl-number') && !node.classList.contains('hl-function') && !node.classList.contains('hl-decorator') && !node.classList.contains('hl-tag') && !node.classList.contains('hl-attribute') && !node.classList.contains('hl-selector') && !node.classList.contains('hl-property') && !node.classList.contains('hl-value')) {
                            hasExternalAdd = true;
                        }
                    }
                });
                if (hasExternalAdd) { shouldRun = true; break; }
            }
            if (shouldRun) {
                observer.disconnect();
                highlightAllPending(document);
                observer.observe(document.body, { childList: true, subtree: true });
            }
        });
        observer.observe(document.body, { childList: true, subtree: true });
    }
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}
