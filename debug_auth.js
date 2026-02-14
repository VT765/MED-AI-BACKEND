// Native fetch is available in Node.js 18+

const BASE_URL = 'http://localhost:3000/api/auth';

async function testAuth() {
    console.log('--- Testing Signup ---');
    const user = {
        username: "Debug User",
        email: `debug_${Date.now()}@test.com`,
        password: "password123"
    };

    try {
        const signupRes = await fetch(`${BASE_URL}/signup`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(user)
        });

        const signupData = await signupRes.json();
        console.log('Signup Status:', signupRes.status);
        console.log('Signup Response:', signupData);

        if (![200, 201].includes(signupRes.status)) {
            console.error("Signup failed, aborting login test.");
            return;
        }

        if (signupData?.verificationRequired) {
            if (!signupData.debugOtp) {
                console.log("Verification required. Check email for OTP, then call /verify-email.");
                return;
            }

            console.log("\n--- Verifying Email ---");
            const verifyRes = await fetch(`${BASE_URL}/verify-email`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email: user.email, otp: signupData.debugOtp })
            });

            const verifyData = await verifyRes.json();
            console.log('Verify Status:', verifyRes.status);
            console.log('Verify Response:', verifyData);

            if (!verifyRes.ok) {
                console.error("Verification failed, aborting login test.");
                return;
            }
        }

        console.log('\n--- Testing Login ---');
        const loginRes = await fetch(`${BASE_URL}/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                email: user.email,
                password: user.password
            })
        });

        const loginData = await loginRes.json();
        console.log('Login Status:', loginRes.status);
        console.log('Login Response:', loginData);

    } catch (err) {
        console.error('Test failed:', err);
    }
}

testAuth();
