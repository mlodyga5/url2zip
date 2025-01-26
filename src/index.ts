// src/index.ts
import { Storage } from '@google-cloud/storage';
import { Firestore } from '@google-cloud/firestore';
import * as crypto from 'crypto';
import * as stream from 'stream';
import * as functions from '@google-cloud/functions-framework';
import fetch from 'node-fetch';

const storage = new Storage();
const firestore = new Firestore();
const BUCKET_NAME = 'your-encrypted-files-bucket';
const SIZE_THRESHOLD = 50 * 1024 * 1024; // 50MB
const ENCRYPTION_KEY = process.env.ENCRYPTION_KEY!;
const IV_LENGTH = 16;

interface EncryptionJob {
  id: string;
  status: 'pending' | 'downloading' | 'encrypting' | 'completed' | 'failed';
  fileUrl: string;
  fileSize: number;
  encryptedFileUrl?: string;
  error?: string;
  createdAt: Date;
  updatedAt: Date;
}

// Main function handler
functions.http('encryptFile', async (req, res) => {
  try {
    const fileUrl = req.query.fileUrl as string;
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
    } else {
      const jobId = await initiateAsyncEncryption(fileUrl, fileSize);
      res.json({
        type: 'async',
        jobId,
        estimatedTime: Math.ceil(fileSize / (1024 * 1024) * 0.5) // rough estimate: 0.5 sec per MB
      });
    }
  } catch (error) {
    console.error('Error processing request:', error);
    res.status(500).json({
      error: error instanceof Error ? error.message : 'An unknown error occurred',
      retryable: true
    });
  }
});

// Status check endpoint
functions.http('checkStatus', async (req, res) => {
  try {
    const jobId = req.query.jobId as string;
    if (!jobId) {
      res.status(400).json({ error: 'jobId is required' });
      return;
    }

    const jobDoc = await firestore.collection('encryption_jobs').doc(jobId).get();
    if (!jobDoc.exists) {
      res.status(404).json({ error: 'Job not found' });
      return;
    }

    const job = jobDoc.data() as EncryptionJob;
    res.json(job);
  } catch (error) {
    res.status(500).json({ 
      error: error instanceof Error ? error.message : 'An unknown error occurred'
    });
  }
});

async function getFileSize(url: string): Promise<number> {
  const response = await fetch(url, { method: 'HEAD' });
  return parseInt(response.headers.get('content-length') || '0');
}

async function handleDirectEncryption(fileUrl: string) {
  const response = await fetch(fileUrl);
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
    response.body!
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

async function initiateAsyncEncryption(fileUrl: string, fileSize: number): Promise<string> {
  const job: EncryptionJob = {
    id: crypto.randomBytes(16).toString('hex'),
    status: 'pending',
    fileUrl,
    fileSize,
    createdAt: new Date(),
    updatedAt: new Date()
  };

  await firestore.collection('encryption_jobs').doc(job.id).set(job);
  
  // Trigger background function
  await fetch(process.env.BACKGROUND_FUNCTION_URL!, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ jobId: job.id })
  });

  return job.id;
}

function getFileNameFromUrl(url: string): string {
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

    const job = jobDoc.data() as EncryptionJob;
    
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
  } catch (error) {
    console.error('Error processing job:', error);
    
    // Update job with error
    await firestore.collection('encryption_jobs').doc(jobId).update({
      status: 'failed',
      error: error instanceof Error ? error.message : 'An unknown error occurred',
      updatedAt: new Date()
    });

    res.status(500).json({ 
      error: error instanceof Error ? error.message : 'An unknown error occurred'
    });
  }
});