import mongoose from 'mongoose';
import dotenv from 'dotenv';
import path from 'path';
import { fileURLToPath } from 'url';

// Resolve __dirname
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Load env directly like server.js
dotenv.config({ path: path.resolve(__dirname, "./.env") });
dotenv.config(); // fallback

const uri = process.env.MONGO_URI;
console.log("Testing with MONGO_URI:", uri);

if (!uri) {
    console.error("No MONGO_URI found!");
    process.exit(1);
}

const testSchema = new mongoose.Schema({
    name: String,
    created: { type: Date, default: Date.now }
});

const TestModel = mongoose.model('TestCollection', testSchema);

async function runTest() {
    try {
        console.log("Connecting to MongoDB...");
        await mongoose.connect(uri);
        console.log("Connected. Inserting test document...");

        const doc = await TestModel.create({ name: "Direct DB Write Test" });
        console.log("Document saved:", doc);

        console.log("Reading back document...");
        const found = await TestModel.findById(doc._id);
        console.log("Document found:", found);

        console.log("TEST PASSED: Database is writable.");
    } catch (error) {
        console.error("TEST FAILED:", error);
    } finally {
        await mongoose.disconnect();
    }
}

runTest();
