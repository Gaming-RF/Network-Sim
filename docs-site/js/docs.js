document.addEventListener('DOMContentLoaded', () => {
    mermaid.initialize({ startOnLoad: true, theme: 'dark' });
    
    // Smooth scroll for TOC
    document.querySelectorAll('#toc a').forEach(link => {
        link.addEventListener('click', e => {
            e.preventDefault();
            const target = document.querySelector(link.getAttribute('href'));
            target.scrollIntoView({ behavior: 'smooth' });
        });
    });
});
