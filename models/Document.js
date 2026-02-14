import mongoose from 'mongoose';

const documentSchema = mongoose.Schema({
    user: {
        type: mongoose.Schema.Types.ObjectId,
        required: true,
        ref: 'User',
    },
    filename: {
        type: String,
        required: true,
    },
    originalName: {
        type: String,
        required: true,
    },
    fileUrl: {
        type: String,
        required: true,
    },
    extractedText: {
        type: String,
    },
}, {
    timestamps: true,
});

const Document = mongoose.model('Document', documentSchema);

export default Document;
