import { ArukasNFCLiteS } from './modules/ArukasNFCLiteS.js';

const POLL_INTERVAL_MS = 500;
const CHATTERING_MS = 30000;
const SUPPORTED_VENDOR_ID = 1356;
const SUPPORTED_PRODUCT_IDS = new Set([1729, 1731, 3528, 3529]);

let nfcDevice = null;
let polling = false;
let lastIdm = '';
let lastIdmAt = 0;
let scanInFlight = false;
let selectedUsbDevice = null;
let isConnected = false;
let isSpeaking = false;

function setStatus(message) {
    const el = document.getElementById('nfc-status');
    if (el) el.textContent = message;
}

function setOverlayVisible(visible) {
    const overlay = document.getElementById('nfc-connection-overlay');
    if (!overlay) return;
    overlay.classList.toggle('is-hidden', !visible);
}

function updateConnectionState(connected) {
    isConnected = connected;
    setOverlayVisible(!connected);
}

function normalizeIdm(idm) {
    return (idm || '').replace(/\s+/g, '').toUpperCase();
}

async function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

function speakStudentId(studentId) {
    return new Promise(resolve => {
        const normalized = String(studentId || '').trim();
        if (!normalized || !window.speechSynthesis || typeof SpeechSynthesisUtterance === 'undefined') {
            isSpeaking = false;
            resolve();
            return;
        }
        isSpeaking = true;
        const utter = new SpeechSynthesisUtterance(`${normalized}番`);
        utter.lang = 'ja-JP';
        utter.rate = 1.0;
        utter.pitch = 1.0;
        utter.volume = 1.0;
        utter.onend = () => {
            isSpeaking = false;
            resolve();
        };
        utter.onerror = () => {
            isSpeaking = false;
            resolve();
        };
        window.speechSynthesis.cancel();
        window.speechSynthesis.speak(utter);
    });
}

function isRegisterOpen() {
    return !!(window.nfcRegisterApp && window.nfcRegisterApp.showPanel);
}

function pushToRegister(idm) {
    if (window.nfcRegisterApp && typeof window.nfcRegisterApp.setNfcId === 'function') {
        window.nfcRegisterApp.setNfcId(idm);
    }
}

function getOfferingId() {
    return window.SELECTED_OFFERING_ID || '';
}

function isIgnorableError(err) {
    return err && err.code === 512;
}

function createCell(value) {
    const td = document.createElement('td');
    td.textContent = value || '';
    return td;
}

function findRowByData(table, data) {
    if (!table || !data) return null;
    const rows = table.querySelectorAll('tbody tr');
    const targetUserId = data.user_id ? String(data.user_id) : '';
    const targetStudentId = data.student_id || '';
    for (const row of rows) {
        if (targetUserId && row.dataset.userId === targetUserId) return row;
        if (targetStudentId && row.dataset.studentId === targetStudentId) return row;
        const cellValue = row.cells[0] ? row.cells[0].textContent.trim() : '';
        if (targetStudentId && cellValue === targetStudentId) return row;
    }
    return null;
}

function updateInRow(row, data) {
    if (!row || !data) return;
    const values = [
        data.student_id || '',
        data.full_name || '',
        data.experiment_day || '',
        data.experiment_group || '',
        data.check_in_time || ''
    ];
    values.forEach((value, index) => {
        if (row.cells[index]) row.cells[index].textContent = value;
    });
}

function updateOutRow(row, data) {
    if (!row || !data) return;
    const values = [
        data.student_id || '',
        data.full_name || '',
        data.experiment_day || '',
        data.experiment_group || '',
        data.check_in_time || '',
        data.check_out_time || ''
    ];
    values.forEach((value, index) => {
        if (row.cells[index]) row.cells[index].textContent = value;
    });
}

function buildInRow(data) {
    const tr = document.createElement('tr');
    if (data.student_id) tr.dataset.studentId = data.student_id;
    if (data.user_id) tr.dataset.userId = String(data.user_id);
    tr.appendChild(createCell(data.student_id));
    tr.appendChild(createCell(data.full_name));
    tr.appendChild(createCell(data.experiment_day));
    tr.appendChild(createCell(data.experiment_group));
    tr.appendChild(createCell(data.check_in_time));
    return tr;
}

function buildOutRow(data) {
    const tr = document.createElement('tr');
    if (data.student_id) tr.dataset.studentId = data.student_id;
    if (data.user_id) tr.dataset.userId = String(data.user_id);
    tr.appendChild(createCell(data.student_id));
    tr.appendChild(createCell(data.full_name));
    tr.appendChild(createCell(data.experiment_day));
    tr.appendChild(createCell(data.experiment_group));
    tr.appendChild(createCell(data.check_in_time));
    tr.appendChild(createCell(data.check_out_time));
    return tr;
}

function applyAttendanceUpdate(data) {
    const inTable = document.getElementById('in-table');
    const outTable = document.getElementById('out-table');
    const inBody = inTable ? inTable.querySelector('tbody') : null;
    const outBody = outTable ? outTable.querySelector('tbody') : null;
    if (!inBody || !outBody) return;

    if (data.action === 'check_in') {
        const outRow = findRowByData(outTable, data);
        if (outRow) outRow.remove();
        let inRow = findRowByData(inTable, data);
        if (!inRow) {
            inRow = buildInRow(data);
            inBody.appendChild(inRow);
        } else {
            updateInRow(inRow, data);
        }
    } else if (data.action === 'check_out') {
        const inRow = findRowByData(inTable, data);
        if (inRow) inRow.remove();
        let outRow = findRowByData(outTable, data);
        if (!outRow) {
            outRow = buildOutRow(data);
            outBody.appendChild(outRow);
        } else {
            updateOutRow(outRow, data);
        }
    }
}

async function requestUsbDevice() {
    if (!navigator.usb) {
        setStatus('WebUSB非対応のブラウザです');
        updateConnectionState(false);
        return null;
    }
    setStatus('USB選択中...');
    const device = await navigator.usb.requestDevice({
        filters: [{ vendorId: SUPPORTED_VENDOR_ID }]
    });
    setStatus('USB選択完了');
    selectedUsbDevice = device;
    return device;
}

function ensureDeviceInfo(device) {
    if (!device || !nfcDevice) return;
    const productId = device.productId;
    if (!(productId in nfcDevice.DEVICEINFOLIST)) {
        nfcDevice.DEVICEINFOLIST[productId] = {
            vendorId: device.vendorId,
            productId: productId,
            modelName: device.productName || 'PaSoRi',
            deviceType: 'External'
        };
    }
    const exists = nfcDevice.DEVICEFILTERS.some(
        entry => entry.vendorId === device.vendorId && entry.productId === productId
    );
    if (!exists) {
        nfcDevice.DEVICEFILTERS.push({ vendorId: device.vendorId, productId: productId });
    }
}

async function disconnectDevice() {
    polling = false;
    if (nfcDevice && typeof nfcDevice.closeUSBDevice === 'function') {
        try {
            await nfcDevice.closeUSBDevice();
        } catch (err) {
            // ignore disconnect errors
        }
    }
    nfcDevice = null;
}

async function connectDevice(options) {
    const userInitiated = options && options.userInitiated === true;
    const startPollingAfter = !options || options.startPolling !== false;
    const deviceOverride = options && options.selectedDevice ? options.selectedDevice : null;
    if (!navigator.usb) {
        setStatus('WebUSB非対応のブラウザです');
        updateConnectionState(false);
        return;
    }
    if (nfcDevice) {
        if (!userInitiated) return;
        await disconnectDevice();
    }
    nfcDevice = new ArukasNFCLiteS({ warning: false });
    nfcDevice.EcL = () => {};
    try {
        if (!userInitiated && !deviceOverride) {
            const devices = await navigator.usb.getDevices();
            const matched = (devices || []).filter(d =>
                d.vendorId === SUPPORTED_VENDOR_ID && SUPPORTED_PRODUCT_IDS.has(d.productId)
            );
            if (matched.length !== 1) {
                setStatus('NFC未接続（接続ボタンで許可）');
                updateConnectionState(false);
                nfcDevice = null;
                return;
            }
        }
        if (deviceOverride) {
            ensureDeviceInfo(deviceOverride);
        }
        await nfcDevice.connectUSBDevice();
        await nfcDevice.openUSBDevice();
        setStatus('NFC接続済み');
        updateConnectionState(true);
        if (startPollingAfter) {
            startPolling();
        }
    } catch (err) {
        nfcDevice = null;
        setStatus('NFC接続失敗');
        updateConnectionState(false);
        if (userInitiated) {
            alert('NFCリーダーの接続に失敗しました');
        }
    }
}

async function handleIdm(idm) {
    if (isSpeaking) return;
    const offeringId = getOfferingId();
    if (!offeringId) {
        setStatus('科目/年度を選択してください');
        return;
    }

    if (isRegisterOpen()) {
        pushToRegister(idm);
        setStatus('NFC登録に反映しました');
        return;
    }

    if (scanInFlight) return;
    scanInFlight = true;
    try {
        const res = await fetch('/attendance/scan_nfc/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': window.CSRF_TOKEN || ''
            },
            body: JSON.stringify({ nfc_id: idm, offering_id: offeringId })
        });
        const data = await res.json();
        if (!res.ok || data.status !== 'ok') {
            alert(data.message || 'NFCの読み取りに失敗しました');
            return;
        }
        const actionLabel = data.action === 'check_in' ? '入室' : '退室';
        setStatus(`${data.student_id || ''} ${data.full_name || ''} ${actionLabel}`.trim());
        applyAttendanceUpdate(data);
        await speakStudentId(data.student_id);
    } catch (err) {
        alert('通信エラーが発生しました');
    } finally {
        scanInFlight = false;
    }
}

async function startPolling() {
    if (polling || !nfcDevice) return;
    polling = true;
    setStatus('NFC待機中');
    while (polling && nfcDevice) {
        try {
            const res = await nfcDevice.pollingLiteS();
            if (nfcDevice.FelicaConfig.Polling === true) {
                const idm = normalizeIdm(res.IDmString);
                if (idm && !isSpeaking) {
                    const now = Date.now();
                    if (idm !== lastIdm || now - lastIdmAt > CHATTERING_MS) {
                        lastIdm = idm;
                        lastIdmAt = now;
                        await handleIdm(idm);
                    }
                }
            }
        } catch (err) {
            if (isIgnorableError(err)) {
                setStatus('NFC待機中');
            } else {
                setStatus('NFC読み取りエラー');
            }
        }
        if (nfcDevice && typeof nfcDevice.sleep === 'function') {
            await nfcDevice.sleep(POLL_INTERVAL_MS);
        } else {
            await sleep(POLL_INTERVAL_MS);
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    setStatus('NFC未接続');
    updateConnectionState(false);
    window.addEventListener('attendance-record-updated', event => {
        const data = event.detail || null;
        if (!data) return;
        applyAttendanceUpdate(data);
        const actionLabel = data.action === 'check_in' ? '入室' : '退室';
        setStatus(`${data.student_id || ''} ${data.full_name || ''} ${actionLabel}（承認反映）`.trim());
    });
    document.addEventListener('click', event => {
        const target = event.target.closest('#nfc-connect-btn');
        if (!target) return;
        (async () => {
            try {
                const device = await requestUsbDevice();
                if (!device) return;
                await connectDevice({ userInitiated: true, startPolling: true, selectedDevice: device });
            } catch (err) {
                setStatus('USB選択キャンセル');
                updateConnectionState(false);
            }
        })();
    });
    if (navigator.usb) {
        navigator.usb.addEventListener('disconnect', () => {
            if (window.speechSynthesis) {
                window.speechSynthesis.cancel();
            }
            isSpeaking = false;
            setStatus('NFC切断');
            nfcDevice = null;
            polling = false;
            updateConnectionState(false);
        });
    }
});
