import mongoose from "mongoose";

const userSchema = mongoose.Schema(
  {
    // ── Firebase identity ────────────────────────────
    firebaseUid: {
      type: String,
      required: true,
      unique: true,
    },

    // ── Auth metadata ────────────────────────────────
    authProvider: {
      type: String,
      enum: ["phone", "google", "email"],
      default: "phone",
      required: true,
    },

    profileComplete: {
      type: Boolean,
      default: false,
    },

    // ── Core identity ────────────────────────────────
    phone: {
      type: String,
      required: true,
      unique: true,
      trim: true,
    },

    username: {
      type: String,
      trim: true,
      default: null,
    },

    email: {
      type: String,
      lowercase: true,
      trim: true,
      default: null,
    },

    // ── Optional password (hashed) ───────────────────
    password: {
      type: String,
      default: null,
    },
  },
  {
    timestamps: true,
  }
);

const User = mongoose.model("User", userSchema);

export default User;
