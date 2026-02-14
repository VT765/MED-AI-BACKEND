import mongoose from 'mongoose';

const databases = ['sam', 'med-ai-db', 'test', 'admin', 'local'];
const baseUri = 'mongodb://localhost:27017';

// Define schema again to ensure we can read it
const userSchema = new mongoose.Schema({
    username: String,
    email: String,
});
const User = mongoose.model('User', userSchema, 'users');

async function checkAllDBs() {
    console.log("🔍 Scanning local MongoDB databases for Users...");

    for (const dbName of databases) {
        const uri = `${baseUri}/${dbName}`;
        try {
            if (mongoose.connection.readyState !== 0) {
                await mongoose.disconnect();
            }
            await mongoose.connect(uri, { serverSelectionTimeoutMS: 2000 });

            const count = await User.countDocuments();

            if (count > 0) {
                console.log(`\n✅ FOUND DATA in '${dbName}': ${count} users`);
                const users = await User.find({});
                users.forEach(u => console.log(`   - ${u.email} (${u.username}) [ID: ${u._id}]`));
            } else {
                console.log(`   - '${dbName}': 0 users`);
            }
        } catch (err) {
            console.log(`   - '${dbName}': Error (${err.message})`);
        }
    }
    await mongoose.disconnect();
    console.log("\nScan complete.");
}

checkAllDBs();
