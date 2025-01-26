"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || function (mod) {
    if (mod && mod.__esModule) return mod;
    var result = {};
    if (mod != null) for (var k in mod) if (k !== "default" && Object.prototype.hasOwnProperty.call(mod, k)) __createBinding(result, mod, k);
    __setModuleDefault(result, mod);
    return result;
};
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
// src/index.ts
const storage_1 = require("@google-cloud/storage");
const firestore_1 = require("@google-cloud/firestore");
const crypto = __importStar(require("crypto"));
const functions = __importStar(require("@google-cloud/functions-framework"));
const node_fetch_1 = __importDefault(require("node-fetch"));
const storage = new storage_1.Storage();
const firestore = new firestore_1.Firestore();
const BUCKET_NAME = 'your-encrypted-files-bucket';
const SIZE_THRESHOLD = 50 * 1024 * 1024; // 50MB
const ENCRYPTION_KEY = process.env.ENCRYPTION_KEY;
const IV_LENGTH = 16;
// Main function handler
functions.http('encryptFile', async (req, res) => {
    try {
        const fileUrl = req.query.fileUrl;
        if (!fileUrl) {
            res.status(400).json({ error: 'fileUrl is required' });
            return;
        }
        const fileSize = await getFileSize(fileUrl);
        if (fileSize < SIZE_THRESHOLD) {
            const result = await handleDirectEncryption(fileUrl);
            res.json({
                type: 'direct',
                encryptedFileUrl: result.encryptedFileUrl
            });
        }
        else {
            const jobId = await initiateAsyncEncryption(fileUrl, fileSize);
            res.json({
                type: 'async',
                jobId,
                estimatedTime: Math.ceil(fileSize / (1024 * 1024) * 0.5) // rough estimate: 0.5 sec per MB
            });
        }
    }
    catch (error) {
        console.error('Error processing request:', error);
        res.status(500).json({
            error: error.message,
            retryable: true
        });
    }
});
// Status check endpoint
functions.http('checkStatus', async (req, res) => {
    try {
        const jobId = req.query.jobId;
        if (!jobId) {
            res.status(400).json({ error: 'jobId is required' });
            return;
        }
        const jobDoc = await firestore.collection('encryption_jobs').doc(jobId).get();
        if (!jobDoc.exists) {
            res.status(404).json({ error: 'Job not found' });
            return;
        }
        const job = jobDoc.data();
        res.json(job);
    }
    catch (error) {
        res.status(500).json({ error: error.message });
    }
});
async function getFileSize(url) {
    const response = await (0, node_fetch_1.default)(url, { method: 'HEAD' });
    return parseInt(response.headers.get('content-length') || '0');
}
async function handleDirectEncryption(fileUrl) {
    const response = await (0, node_fetch_1.default)(fileUrl);
    const fileName = getFileNameFromUrl(fileUrl);
    const encryptedFileName = `encrypted-${fileName}-${Date.now()}`;
    const iv = crypto.randomBytes(IV_LENGTH);
    const cipher = crypto.createCipheriv('aes-256-cbc', Buffer.from(ENCRYPTION_KEY), iv);
    const bucket = storage.bucket(BUCKET_NAME);
    const file = bucket.file(encryptedFileName);
    const writeStream = file.createWriteStream({
        metadata: {
            contentType: response.headers.get('content-type') || 'application/octet-stream',
            metadata: {
                iv: iv.toString('hex')
            }
        }
    });
    await new Promise((resolve, reject) => {
        response.body
            .pipe(cipher)
            .pipe(writeStream)
            .on('finish', resolve)
            .on('error', reject);
    });
    const [url] = await file.getSignedUrl({
        version: 'v4',
        action: 'read',
        expires: Date.now() + 15 * 60 * 1000 // 15 minutes
    });
    return { encryptedFileUrl: url };
}
async function initiateAsyncEncryption(fileUrl, fileSize) {
    const job = {
        id: crypto.randomBytes(16).toString('hex'),
        status: 'pending',
        fileUrl,
        fileSize,
        createdAt: new Date(),
        updatedAt: new Date()
    };
    await firestore.collection('encryption_jobs').doc(job.id).set(job);
    // Trigger background function
    await (0, node_fetch_1.default)(process.env.BACKGROUND_FUNCTION_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ jobId: job.id })
    });
    return job.id;
}
function getFileNameFromUrl(url) {
    const urlParts = new URL(url);
    return urlParts.pathname.split('/').pop() || 'unknown';
}
// Background processing function
functions.http('processEncryption', async (req, res) => {
    const { jobId } = req.body;
    try {
        const jobRef = firestore.collection('encryption_jobs').doc(jobId);
        const jobDoc = await jobRef.get();
        if (!jobDoc.exists) {
            res.status(404).json({ error: 'Job not found' });
            return;
        }
        const job = jobDoc.data();
        // Update status to downloading
        await jobRef.update({
            status: 'downloading',
            updatedAt: new Date()
        });
        // Process the file
        const result = await handleDirectEncryption(job.fileUrl);
        // Update job with success
        await jobRef.update({
            status: 'completed',
            encryptedFileUrl: result.encryptedFileUrl,
            updatedAt: new Date()
        });
        res.json({ success: true });
    }
    catch (error) {
        console.error('Error processing job:', error);
        // Update job with error
        await firestore.collection('encryption_jobs').doc(jobId).update({
            status: 'failed',
            error: error.message,
            updatedAt: new Date()
        });
        res.status(500).json({ error: error.message });
    }
});
