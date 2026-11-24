const hre = require("hardhat");

async function main() {
  // This MUST be the PermissionedNVP token address
  const TOKEN_ADDRESS = "0xE4313472EF0C2C8BF5Fe9a0fF154F604481984f4"; // <--- MAKE SURE THIS IS CORRECT
  
  // The wallet you want to allow
  const WALLET_TO_WHITELIST = "0x66e9a79aDb97Bae948E97c09F1eE555f6E4c6767"; 

  const Token = await hre.ethers.getContractFactory("PermissionedNVP");
  const token = await Token.attach(TOKEN_ADDRESS);

  console.log(`Attempting to whitelist ${WALLET_TO_WHITELIST} on token ${TOKEN_ADDRESS}...`);
  const tx = await token.setWhitelisted(WALLET_TO_WHITELIST, true);
  console.log("Transaction sent! Hash:", tx.hash);
  await tx.wait();
  console.log("✅ Successfully whitelisted on-chain!");
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
