import express from "express";
import cors from "cors";
import dotenv from "dotenv";
import connectDB from "./config/db.js";
import admin from "./config/firebase.js";
import bcrypt from "bcryptjs";
import User from "./models/User.js";
import Document from "./models/Document.js";
import { protect } from "./middleware/auth.js";
import upload from "./middleware/upload.js";
import fs from "fs";
import path from "path";
import OpenAI from "openai";
import { createRequire } from "module";
import { fileURLToPath } from "url";
import CSSMatrix from "@thednp/dommatrix";

if (typeof globalThis.DOMMatrix === "undefined") {
  globalThis.DOMMatrix = CSSMatrix;
}

const require = createRequire(import.meta.url);
const pdf = require("pdf-parse");

// Resolve __dirname in ES modules
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Load .env from backend folder, then project root, so either location works
dotenv.config({ path: path.resolve(__dirname, "./.env") });
dotenv.config({ path: path.resolve(__dirname, "../.env") });
dotenv.config();

if (!process.env.MONGO_URI) {
  console.error(
    "MONGO_URI is not set. Please create a .env file in the project root or backend folder with MONGO_URI set to your MongoDB connection string."
  );
}

if (!process.env.OPENAI_API_KEY) {
  console.warn(
    "OPENAI_API_KEY is not set. The /api/chat endpoint will not work until you add OPENAI_API_KEY to your .env."
  );
}

connectDB();

const openai = process.env.OPENAI_API_KEY
  ? new OpenAI({ apiKey: process.env.OPENAI_API_KEY })
  : null;

const app = express();
const PORT = process.env.PORT || 3000;

// middleware
app.use(cors({
  origin: "*",
  credentials: true
}));
app.use(express.json());
app.use((req, res, next) => {
  console.log(`[${new Date().toISOString()}] ${req.method} ${req.url}`);
  next();
});
app.use('/uploads', express.static('uploads'));

// 🔐 FIREBASE PHONE AUTH — VERIFY & CREATE USER
app.post("/api/auth/verify-phone", async (req, res) => {
  const authHeader = req.headers.authorization;

  if (!authHeader || !authHeader.startsWith("Bearer ")) {
    return res.status(401).json({ authenticated: false, message: "Missing or invalid Authorization header" });
  }

  const idToken = authHeader.split(" ")[1];

  try {
    const decoded = await admin.auth().verifyIdToken(idToken);

    if (!decoded.phone_number) {
      return res.status(400).json({ authenticated: false, message: "Token does not contain a phone number" });
    }

    const phone = decoded.phone_number;
    const firebaseUid = decoded.uid;

    // Find existing user or create a new one
    let user = await User.findOne({ firebaseUid });
    let isNewUser = false;

    if (!user) {
      user = await User.create({
        firebaseUid,
        phone,
        authProvider: "phone",
        profileComplete: false,
        username: null,
        email: null,
        password: null,
      });
      isNewUser = true;
      console.log("New user created via Firebase:", user._id);
    }

    res.json({
      authenticated: true,
      profileComplete: user.profileComplete,
      isNewUser,
      user: {
        id: user._id,
        phone: user.phone,
        username: user.username,
        email: user.email || undefined,
        authProvider: user.authProvider,
      },
    });
  } catch (error) {
    console.error("Firebase verify-phone error:", error);
    res.status(401).json({ authenticated: false, message: "Invalid Firebase token", error: error.message });
  }
});

// 📝 COMPLETE PROFILE — set username, email, optional password
app.post("/api/auth/complete-profile", protect, async (req, res) => {
  try {
    const user = req.user;

    // Prevent double-completion (idempotency guard)
    if (user.profileComplete) {
      return res.status(400).json({ message: "Profile is already complete" });
    }

    const { username, email, password } = req.body;

    // ── Validate required fields ──
    if (!username || typeof username !== "string" || !username.trim()) {
      return res.status(400).json({ message: "Username is required" });
    }
    if (!email || typeof email !== "string" || !email.trim()) {
      return res.status(400).json({ message: "Email is required" });
    }

    const trimmedUsername = username.trim();
    const trimmedEmail = email.trim().toLowerCase();

    // ── Validate email format ──
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(trimmedEmail)) {
      return res.status(400).json({ message: "Invalid email format" });
    }

    // ── Check uniqueness ──
    const existingUsername = await User.findOne({ username: trimmedUsername, _id: { $ne: user._id } });
    if (existingUsername) {
      return res.status(409).json({ message: "Username is already taken" });
    }

    const existingEmail = await User.findOne({ email: trimmedEmail, _id: { $ne: user._id } });
    if (existingEmail) {
      return res.status(409).json({ message: "Email is already in use" });
    }

    // ── Update user ──
    user.username = trimmedUsername;
    user.email = trimmedEmail;
    user.profileComplete = true;

    // Hash password if provided
    if (password && typeof password === "string" && password.length >= 6) {
      const salt = await bcrypt.genSalt(10);
      user.password = await bcrypt.hash(password, salt);
    } else if (password) {
      return res.status(400).json({ message: "Password must be at least 6 characters" });
    }

    await user.save();

    res.json({
      message: "Profile completed successfully",
      profileComplete: true,
      user: {
        id: user._id,
        phone: user.phone,
        username: user.username,
        email: user.email,
        authProvider: user.authProvider,
      },
    });
  } catch (error) {
    console.error("Complete profile error:", error);
    res.status(500).json({ message: "Server error", error: error.message });
  }
});

// 👤 GET CURRENT USER
app.get("/api/auth/me", protect, async (req, res) => {
  res.json({
    user: {
      id: req.user._id,
      username: req.user.username,
      phone: req.user.phone,
      email: req.user.email || undefined,
      authProvider: req.user.authProvider,
      profileComplete: req.user.profileComplete,
      createdAt: req.user.createdAt,
    },
  });
});

// 📄 UPLOAD DOCUMENT
app.post("/api/documents/upload", protect, upload.single("file"), async (req, res) => {
  if (!req.file) {
    return res.status(400).json({ message: "No file uploaded" });
  }

  try {
    const dataBuffer = fs.readFileSync(req.file.path);
    const data = await pdf(dataBuffer);

    // Create document in DB
    const document = await Document.create({
      user: req.user._id,
      filename: req.file.filename,
      originalName: req.file.originalname,
      fileUrl: req.file.path,
      extractedText: data.text,
    });

    res.status(201).json({
      message: "File uploaded and processed successfully",
      document: {
        id: document._id,
        filename: document.filename,
        textPreview: document.extractedText.substring(0, 200) + "..."
      }
    });

  } catch (error) {
    console.error(error);
    res.status(500).json({ message: "File processing failed", error: error.message });
  }
});

// 🤖 AI CHAT
app.post("/api/chat", protect, async (req, res) => {
  const { question, documentId } = req.body;

  if (!question || !documentId) {
    return res.status(400).json({ message: "Question and Document ID required" });
  }

  try {
    const document = await Document.findById(documentId);

    if (!document) {
      return res.status(404).json({ message: "Document not found" });
    }

    if (document.user.toString() !== req.user._id.toString()) {
      return res.status(401).json({ message: "Not authorized to access this document" });
    }

    if (!openai) {
      return res.status(503).json({
        message: "AI chat is not available. Add OPENAI_API_KEY to your .env to enable it.",
      });
    }

    // Context window limit handling (rudimentary)
    const contextText = document.extractedText.substring(0, 10000);

    const completion = await openai.chat.completions.create({
      messages: [
        { role: "system", content: "You are a helpful medical assistant. Answer the user's question based on the provided document text. Disclaimer: This is not medical advice. Consult a licensed professional." },
        { role: "user", content: `Document Text: ${contextText}\n\nQuestion: ${question}` }
      ],
      model: "gpt-3.5-turbo",
    });

    const answer = completion.choices[0].message.content;

    res.json({
      answer: answer + "\n\n**Disclaimer: This is not medical advice. Consult a licensed professional.**"
    });

  } catch (error) {
    console.error("OpenAI Error:", error);
    res.status(500).json({ message: "AI Chat failed", error: error.message });
  }
});

// server start
app.listen(PORT, () => {
  console.log(`Server running on http://localhost:${PORT}`);
});
