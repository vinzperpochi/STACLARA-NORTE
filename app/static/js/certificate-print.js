'use strict';

const documentFrame = document.getElementById('certificate-frame');
const printButton = document.getElementById('print-certificate');
const pdfButton = document.getElementById('download-document');
const outputStatus = document.getElementById('document-output-status');

async function documentPages() {
    const source = documentFrame.contentDocument;
    const pages = [...(source?.querySelectorAll('.page') ?? [])];
    if (!pages.length) throw new Error('Document preview unavailable');
    await source.fonts.ready;
    await Promise.all([...source.images].map(image => image.decode()));
    return pages;
}

async function printDocument() {
    try {
        await documentPages();
        outputStatus.textContent = '';
        documentFrame.contentWindow.focus();
        documentFrame.contentWindow.print();
    } catch {
        outputStatus.textContent = 'The template is unavailable. Reload the preview and try again.';
    }
}

async function downloadDocument() {
    pdfButton.disabled = true;
    outputStatus.textContent = 'Generating PDF…';
    try {
        const pages = await documentPages();
        const pdf = new window.jspdf.jsPDF({ unit: 'mm', format: 'a4', compress: true });
        for (const [index, page] of pages.entries()) {
            const canvas = await window.html2canvas(page, {
                scale: 2.5, backgroundColor: '#fff', logging: false
            });
            if (index) pdf.addPage();
            pdf.addImage(canvas, 'PNG', 0, 0, 210, 297, undefined, 'FAST');
            canvas.width = canvas.height = 0;
        }
        pdf.save(document.title.replace(/[^a-z0-9_-]/gi, '-') + '.pdf');
        outputStatus.textContent = 'PDF ready.';
    } catch {
        outputStatus.textContent = 'PDF generation failed. Use Print and select Save as PDF.';
    } finally {
        pdfButton.disabled = false;
    }
}

function handleFrameReady() {
    if (documentFrame.dataset.downloadNow === 'yes' && pdfButton) {
        documentFrame.dataset.downloadNow = 'no';
        downloadDocument();
    } else if (documentFrame.dataset.printNow === 'yes') {
        documentFrame.dataset.printNow = 'no';
        printDocument();
    }
}

printButton.addEventListener('click', printDocument);
pdfButton?.addEventListener('click', downloadDocument);
documentFrame.addEventListener('load', handleFrameReady);
if (documentFrame.contentDocument?.readyState === 'complete' &&
    documentFrame.contentDocument.querySelector('.page')) handleFrameReady();
