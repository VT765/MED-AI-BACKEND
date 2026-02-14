import mongoose from "mongoose";
import dotenv from "dotenv";
import path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

dotenv.config({ path: path.resolve(__dirname, "../.env") });
dotenv.config();

const uri = process.env.MONGO_URI;

if (!uri) {
  console.error("MONGO_URI is not set. Add it to backend/.env or project root .env.");
  process.exit(1);
}

async function run() {
  await mongoose.connect(uri);
  const users = mongoose.connection.collection("users");

  const result = await users.updateMany(
    { name: { $exists: true } },
    [
      { $set: { username: { $ifNull: ["$username", "$name"] } } },
      { $unset: "name" }
    ]
  );

  console.log(
    `Rename complete. Matched: ${result.matchedCount}, Modified: ${result.modifiedCount}`
  );

  await mongoose.disconnect();
}

run().catch((err) => {
  console.error("Migration failed:", err);
  process.exit(1);
});
