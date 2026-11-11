'use strict';
const certificateFrame = document.getElementById('certificate-frame');
function printCertificate() { certificateFrame.contentWindow.focus(); certificateFrame.contentWindow.print(); }
document.getElementById('print-certificate').addEventListener('click', printCertificate);
certificateFrame.addEventListener('load', () => { if (certificateFrame.dataset.printNow === 'yes') printCertificate(); });
