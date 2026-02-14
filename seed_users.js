import mongoose from 'mongoose';
import dotenv from 'dotenv';
import path from 'path';
import { fileURLToPath } from 'url';
import bcrypt from 'bcryptjs';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Load env from project root
dotenv.config({ path: path.resolve(__dirname, "./.env") });

const uri = process.env.MONGO_URI || 'mongodb://localhost:27017/sam';
console.log("Seeding to:", uri);

const userSchema = new mongoose.Schema({
    username: { type: String, required: true },
    email: { type: String, required: true, unique: true },
    password: { type: String, required: true },
    emailVerified: { type: Boolean, default: true },
    emailVerifiedAt: { type: Date, default: Date.now }
}, { timestamps: true });

const User = mongoose.model('User', userSchema);

const dummyUsers = [
    { username: "Alice Test", email: "alice@test.com", password: "password123" },
    { username: "Bob Demo", email: "bob@demo.com", password: "password123" },
    { username: "Charlie Dev", email: "charlie@dev.com", password: "password123" }
];

async function seedUsers() {
    try {
        await mongoose.connect(uri);
        console.log("Connected to MongoDB.");

        // Clear existing test users to avoid duplicates if re-run
        await User.deleteMany({ email: { $in: dummyUsers.map(u => u.email) } });
        console.log("Cleaned up old test users.");

        const hashedUsers = await Promise.all(dummyUsers.map(async (u) => {
            const hashedPassword = await bcrypt.hash(u.password, 10);
            return { ...u, password: hashedPassword };
        }));

        const result = await User.insertMany(hashedUsers);
        console.log(`\n✅ Successfully added ${result.length} dummy users:`);
        result.forEach(u => console.log(`   - ${u.username} (${u.email})`));

        console.log("\n👉 Go to MongoDB Compass and check the 'users' collection in the 'sam' database (or verify your MONGO_URI).");

    } catch (error) {
        console.error("Error seeding users:", error);
    } finally {
        await mongoose.disconnect();
    }
}

seedUsers();
