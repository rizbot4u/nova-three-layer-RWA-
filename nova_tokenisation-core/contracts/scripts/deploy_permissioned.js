const hre = require("hardhat");

async function main() {
  const [deployer] = await hre.ethers.getSigners();
  console.log("Deploying PermissionedNVP from:", deployer.address);

  const Treasury = process.env.TREASURY_WALLET_ADDRESS;
  if (!Treasury) throw new Error("TREASURY_WALLET_ADDRESS env not set");

  const Factory = await hre.ethers.getContractFactory("PermissionedNVP");
  const token = await Factory.deploy(
    "Permissioned NVP",
    "NVP-2",
    Treasury,
    deployer.address
  );
  await token.waitForDeployment();

  const addr = await token.getAddress();
  console.log("PermissionedNVP deployed at:", addr);
  console.log("Explorer:", `https://basescan.org/address/${addr}`);
}

main().catch((e) => { console.error(e); process.exit(1); });
