// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

contract PermissionedNVP is ERC20, Ownable {
    mapping(address => bool) public whitelisted;
    mapping(address => uint256) public lockupUntil;

    address public treasury;

    event WhitelistUpdated(address indexed wallet, bool allowed);
    event LockupUpdated(address indexed wallet, uint256 until);
    event TransferBlocked(address indexed from, address indexed to, string reason);

    constructor(
        string memory name_,
        string memory symbol_,
        address treasury_,
        address initialOwner
    ) ERC20(name_, symbol_) Ownable(initialOwner) {
        treasury = treasury_;
        whitelisted[treasury_] = true;
    }

    function setTreasury(address t) external onlyOwner {
        treasury = t;
        whitelisted[t] = true;
    }

    function setWhitelisted(address wallet, bool allowed) external onlyOwner {
        whitelisted[wallet] = allowed;
        emit WhitelistUpdated(wallet, allowed);
    }

    function setWhitelistedBatch(address[] calldata wallets, bool allowed) external onlyOwner {
        for (uint256 i = 0; i < wallets.length; i++) {
            whitelisted[wallets[i]] = allowed;
            emit WhitelistUpdated(wallets[i], allowed);
        }
    }

    function setLockup(address wallet, uint256 until) external onlyOwner {
        lockupUntil[wallet] = until;
        emit LockupUpdated(wallet, until);
    }

    function mint(address to, uint256 amount) external onlyOwner {
        _mint(to, amount);
    }

    function burn(address from, uint256 amount) external onlyOwner {
        _burn(from, amount);
    }

    function _update(address from, address to, uint256 value) internal override {
        if (from != address(0)) {
            if (!whitelisted[from]) {
                emit TransferBlocked(from, to, "sender_not_whitelisted");
                revert("PermissionedNVP: sender not whitelisted");
            }
            if (lockupUntil[from] > 0 && block.timestamp < lockupUntil[from]) {
                emit TransferBlocked(from, to, "sender_locked_up");
                revert("PermissionedNVP: sender locked up");
            }
        }
        if (to != address(0) && to != treasury) {
            if (!whitelisted[to]) {
                emit TransferBlocked(from, to, "receiver_not_whitelisted");
                revert("PermissionedNVP: receiver not whitelisted");
            }
        }
        super._update(from, to, value);
    }
}
