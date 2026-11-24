const { ethers } = require("ethers");
require("dotenv").config();

async function main() {
    const provider = new ethers.JsonRpcProvider("https://mainnet.base.org");
    const wallet = new ethers.Wallet(process.env.TREASURY_PRIVATE_KEY, provider);

    // CHANGE THIS: The Property Share Contract
    const TOKEN_ADDRESS = "0x11b229E0F4a0DAee8B8Bf20BdED941b7ba4E8C4c"; 
    const WALLET_TO_WHITELIST = "0x66e9a79aDb97Bae948E97c09F1eE555f6E4c6767"; 

    // Note: The function signature here might be whitelist(address) based on the selector 0x9b19251a
    const abi = [
        "function whitelist(address account) external",
        "function setWhitelisted(address wallet, bool allowed) external" // Keeping fallback
    ];

    const contract = new ethers.Contract(TOKEN_ADDRESS, abi, wallet);

    console.log(`Sending whitelist transaction for ${WALLET_TO_WHITELIST}...`);
    
    try {
        // We use gasLimit to bypass the estimateGas bug on Termux
        const tx = await contract.whitelist(WALLET_TO_WHITELIST, { gasLimit: 150000 });
        console.log("Transaction sent! Hash:", tx.hash);
        const receipt = await tx.wait();
        console.log(`✅ Successfully whitelisted in block ${receipt.blockNumber}!`);
    } catch (error) {
        console.error("Transaction failed. Full error:");
        console.error(error);
    }
}

main();
