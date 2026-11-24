// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/**
 * @title NovaDvPSettlementV2
 * @notice True atomic Delivery-versus-Payment for Nova Global Keys.
 *         Both legs execute in a single transaction, or both revert.
 *
 *         V2 additions over V1:
 *           - Authorized relayer model (only bridge can settle)
 *           - On-chain orderId replay protection (each trade settles once)
 *           - ReentrancyGuard on settleDvP
 *           - SafeERC20 for maximum ERC-20 compatibility
 *           - Relayer can be rotated by owner
 *
 * @dev V1 (0x665714c657e35e0a571D902a542a30FC9A026DA5) is preserved as
 *      evidence of a successful atomic settlement. V2 is deployed separately.
 */
contract NovaDvPSettlementV2 is ReentrancyGuard {
    using SafeERC20 for IERC20;

    IERC20 public immutable dkhyr;
    IERC20 public immutable nvp1;

    address public owner;
    address public relayer;

    uint256 public feeBps = 0;

    /// @notice On-chain record of settled order IDs (replay protection)
    mapping(bytes32 => bool) public settled;

    event DvPSettled(
        bytes32 indexed orderId,
        bytes32 indexed settlementId,
        address indexed buyer,
        address seller,
        uint256 dkhyrAmount,
        uint256 shareAmount,
        uint256 timestamp
    );

    event RelayerUpdated(address indexed previousRelayer, address indexed newRelayer);
    event FeeUpdated(uint256 oldFeeBps, uint256 newFeeBps);
    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);

    modifier onlyOwner() {
        require(msg.sender == owner, "NovaDvP: not owner");
        _;
    }

    modifier onlyRelayer() {
        require(msg.sender == relayer || msg.sender == owner, "NovaDvP: not relayer");
        _;
    }

    constructor(
        address _dkhyr,
        address _nvp1,
        address _owner,
        address _relayer
    ) {
        require(_dkhyr != address(0), "NovaDvP: dkhyr=0");
        require(_nvp1 != address(0), "NovaDvP: nvp1=0");
        require(_owner != address(0), "NovaDvP: owner=0");
        require(_relayer != address(0), "NovaDvP: relayer=0");
        dkhyr = IERC20(_dkhyr);
        nvp1 = IERC20(_nvp1);
        owner = _owner;
        relayer = _relayer;
    }

    /**
     * @notice Atomic DvP settlement.
     * @dev Only callable by authorized relayer (the bridge).
     *      Each orderId can only be settled once.
     *
     * @param orderId       Off-chain order ID (unique). Prevents duplicate settlement.
     * @param buyer         Address receiving NVP-1 shares
     * @param seller        Address receiving DKHYR payment
     * @param dkhyrAmount   DKHYR amount buyer pays
     * @param shareAmount   NVP-1 shares seller delivers
     */
    function settleDvP(
        bytes32 orderId,
        address buyer,
        address seller,
        uint256 dkhyrAmount,
        uint256 shareAmount
    ) external onlyRelayer nonReentrant returns (bytes32 settlementId) {
        require(orderId != bytes32(0), "NovaDvP: orderId=0");
        require(!settled[orderId], "NovaDvP: order already settled");
        require(buyer != address(0), "NovaDvP: buyer=0");
        require(seller != address(0), "NovaDvP: seller=0");
        require(buyer != seller, "NovaDvP: buyer=seller");
        require(dkhyrAmount > 0, "NovaDvP: dkhyrAmount=0");
        require(shareAmount > 0, "NovaDvP: shareAmount=0");

        // Mark settled BEFORE external calls (reentrancy safety)
        settled[orderId] = true;

        // LEG 1: DKHYR moves buyer → seller
        dkhyr.safeTransferFrom(buyer, seller, dkhyrAmount);

        // LEG 2: NVP-1 moves seller → buyer
        // If this fails (whitelist, balance, allowance), the entire tx
        // reverts, including LEG 1 and the settled[orderId] write.
        nvp1.safeTransferFrom(seller, buyer, shareAmount);

        settlementId = keccak256(
            abi.encodePacked(
                block.chainid,
                address(this),
                orderId,
                buyer,
                seller,
                dkhyrAmount,
                shareAmount,
                block.timestamp,
                block.number
            )
        );

        emit DvPSettled(
            orderId,
            settlementId,
            buyer,
            seller,
            dkhyrAmount,
            shareAmount,
            block.timestamp
        );

        return settlementId;
    }

    /**
     * @notice Preview settlement before submission.
     * @dev Read-only. Does not consume gas. Does not mark order as settled.
     */
    function previewSettlement(
        bytes32 orderId,
        address buyer,
        address seller,
        uint256 dkhyrAmount,
        uint256 shareAmount
    ) external view returns (
        bool ok,
        string memory reason,
        uint256 buyerDkhyrBalance,
        uint256 buyerDkhyrAllowance,
        uint256 sellerNvp1Balance,
        uint256 sellerNvp1Allowance
    ) {
        if (orderId == bytes32(0)) return (false, "orderId=0", 0, 0, 0, 0);
        if (settled[orderId]) return (false, "order already settled", 0, 0, 0, 0);
        if (buyer == address(0)) return (false, "buyer=0", 0, 0, 0, 0);
        if (seller == address(0)) return (false, "seller=0", 0, 0, 0, 0);
        if (buyer == seller) return (false, "buyer=seller", 0, 0, 0, 0);

        buyerDkhyrBalance = dkhyr.balanceOf(buyer);
        buyerDkhyrAllowance = dkhyr.allowance(buyer, address(this));
        sellerNvp1Balance = nvp1.balanceOf(seller);
        sellerNvp1Allowance = nvp1.allowance(seller, address(this));

        if (dkhyrAmount == 0) return (false, "dkhyrAmount=0", buyerDkhyrBalance, buyerDkhyrAllowance, sellerNvp1Balance, sellerNvp1Allowance);
        if (shareAmount == 0) return (false, "shareAmount=0", buyerDkhyrBalance, buyerDkhyrAllowance, sellerNvp1Balance, sellerNvp1Allowance);
        if (buyerDkhyrBalance < dkhyrAmount) return (false, "buyer DKHYR balance too low", buyerDkhyrBalance, buyerDkhyrAllowance, sellerNvp1Balance, sellerNvp1Allowance);
        if (buyerDkhyrAllowance < dkhyrAmount) return (false, "buyer DKHYR allowance too low", buyerDkhyrBalance, buyerDkhyrAllowance, sellerNvp1Balance, sellerNvp1Allowance);
        if (sellerNvp1Balance < shareAmount) return (false, "seller NVP-1 balance too low", buyerDkhyrBalance, buyerDkhyrAllowance, sellerNvp1Balance, sellerNvp1Allowance);
        if (sellerNvp1Allowance < shareAmount) return (false, "seller NVP-1 allowance too low", buyerDkhyrBalance, buyerDkhyrAllowance, sellerNvp1Balance, sellerNvp1Allowance);

        return (true, "", buyerDkhyrBalance, buyerDkhyrAllowance, sellerNvp1Balance, sellerNvp1Allowance);
    }

    /// @notice Check whether an order has been settled
    function isSettled(bytes32 orderId) external view returns (bool) {
        return settled[orderId];
    }

    // ── Admin ────────────────────────────────────────────────

    function setRelayer(address _relayer) external onlyOwner {
        require(_relayer != address(0), "NovaDvP: relayer=0");
        address prev = relayer;
        relayer = _relayer;
        emit RelayerUpdated(prev, _relayer);
    }

    function setFeeBps(uint256 _feeBps) external onlyOwner {
        require(_feeBps <= 500, "NovaDvP: fee > 5%");
        uint256 old = feeBps;
        feeBps = _feeBps;
        emit FeeUpdated(old, _feeBps);
    }

    function transferOwnership(address newOwner) external onlyOwner {
        require(newOwner != address(0), "NovaDvP: newOwner=0");
        emit OwnershipTransferred(owner, newOwner);
        owner = newOwner;
    }
}
