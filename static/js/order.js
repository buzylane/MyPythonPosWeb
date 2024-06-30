document.addEventListener('DOMContentLoaded', function () {
    // Set focus to Product Code field when the page loads
    document.getElementById('Product_Code').focus();

    // Set default values for Order Amount, Total Discount, Payment Status, and Order Status
    setDefaultValues();

    // Attach event listeners
    attachEventListeners();

    // Fetch order details if order_id is present in the URL
    const orderId = new URLSearchParams(window.location.search).get('order_id');
    if (orderId) {
        fetchOrderDetails(orderId);
    }
});

function setDefaultValues() {
    document.getElementById('order_amount').value = defaultOrderAmount;
    document.getElementById('total_discount').value = defaultTotalDiscount;
    document.getElementById('payment_status').value = 'Pending Payment';
    document.getElementById('order_status').value = 'Pending';
}

function attachEventListeners() {
    document.getElementById('Quantity').addEventListener('input', calculateTotalAmount);
    document.getElementById('Unit_Price').addEventListener('input', calculateTotalAmount);
    document.getElementById('discount').addEventListener('input', calculateTotalAmount);
    document.getElementById('Variant').addEventListener('change', function () {
        const productName = document.getElementById('Product').value;
        const variant = this.value;
        fetchVariantDetails(productName, variant);
        document.getElementById('Quantity').focus(); // Shift focus to Quantity
    });

    setupAutocomplete();
}

function setupAutocomplete() {
    $("#Customer_Name").autocomplete({
        source: function (request, response) {
            $.ajax({
                url: "/search_customers",
                data: { query: request.term.toLowerCase() },
                success: function (data) {
                    response($.map(data, function (item) {
                        return {
                            label: item.name + " - " + item.contact,
                            value: item.name,
                            contact: item.contact,
                            id: item.id // Include customer_id
                        };
                    }));
                }
            });
        },
        minLength: 2,
        select: function (event, ui) {
            $("#Customer_Name").val(ui.item.value);
            $("#Customer_Contact").val(ui.item.contact);
            $("#Customer_ID").val(ui.item.id); // Set the hidden input value to customer_id
            return false;
        }
    });

    $("#Product_Code").autocomplete({
        source: function (request, response) {
            $.ajax({
                url: "/search_products",
                data: { query: request.term.toLowerCase() },
                success: function (data) {
                    response($.map(data, function (item) {
                        return {
                            label: item[0], // Display only productid
                            value: item[0]
                        };
                    }));
                }
            });
        },
        minLength: 2,
        select: function (event, ui) {
            $("#Product_Code").val(ui.item.value);
            fetchProductDetails(ui.item.value);
            $("#Quantity").focus(); // Shift focus to Quantity
            return false;
        }
    });

    $("#Product").autocomplete({
        source: function (request, response) {
            $.ajax({
                url: "/search_products",
                data: { query: request.term.toLowerCase() },
                success: function (data) {
                    response($.map(data, function (item) {
                        return {
                            label: item[1], // Display product name
                            value: item[1],
                            product_code: item[0] // Fetch product code as well
                        };
                    }));
                }
            });
        },
        minLength: 2,
        select: function (event, ui) {
            $("#Product").val(ui.item.value);
            $("#Product_Code").val(ui.item.product_code); // Set product code
            fetchProductDetailsByName(ui.item.value);
            fetchVariants(ui.item.value);
            $("#Quantity").focus(); // Shift focus to Quantity
            return false;
        }
    });
}

function fetchProductDetails(productCode) {
    fetch(`/get_product_details?product_code=${productCode}`)
        .then(response => response.json())
        .then(data => {
            const productName = data.product_name;
            document.getElementById('Product').value = productName;
            document.getElementById('Unit_Price').value = data.unit_price;
            document.getElementById('discount').value = data.discount;
            fetchVariants(productName); // Fetch variants based on product name
            calculateTotalAmount();
        })
        .catch(error => console.error('Error fetching product details:', error));
}

function fetchProductDetailsByName(productName) {
    fetch(`/get_product_details_by_name?product_name=${productName}`)
        .then(response => response.json())
        .then(data => {
            document.getElementById('Product_Code').value = data.product_code;
            document.getElementById('Unit_Price').value = data.unit_price;
            document.getElementById('discount').value = data.discount;
            fetchVariants(productName); // Fetch variants based on product name
            calculateTotalAmount();
        })
        .catch(error => console.error('Error fetching product details:', error));
}

function fetchVariants(productName) {
    fetch(`/get_variants?product_name=${productName}`)
        .then(response => response.json())
        .then(data => {
            var variantSelect = document.getElementById('Variant');
            variantSelect.innerHTML = ''; // Clear existing options
            data.forEach(function (variant) {
                var option = document.createElement('option');
                option.value = variant;
                option.text = variant;
                variantSelect.add(option);
            });
        })
        .catch(error => console.error('Error fetching variants:', error));
}

function fetchVariantDetails(productName, variant) {
    fetch(`/get_variant_details?product_name=${encodeURIComponent(productName)}&variant=${encodeURIComponent(variant)}`)
        .then(response => response.json())
        .then(data => {
            if (data.unit_price !== undefined && data.discount !== undefined && data.product_code !== undefined) {
                document.getElementById('Product_Code').value = data.product_code;
                document.getElementById('Unit_Price').value = data.unit_price;
                document.getElementById('discount').value = data.discount;
                calculateTotalAmount(); // Recalculate the total amount based on new unit price and discount
            } else {
                console.error('Failed to fetch variant details');
                alert('Failed to fetch details for the selected variant.');
            }
        })
        .catch(error => {
            console.error('Error fetching variant details:', error);
            alert('Error fetching details for the selected variant.');
        });
}

function calculateTotalAmount() {
    const quantity = document.getElementById('Quantity').value;
    const unitPrice = document.getElementById('Unit_Price').value;
    const discount = document.getElementById('discount').value;
    const totalAmount = (quantity * unitPrice) - discount;
    document.getElementById('Total_Amount').value = totalAmount.toFixed(2);

    updateTotals(); // Update the totals in the summary section
}

function addProductRow() {
    const productCode = document.getElementById('Product_Code').value;
    const productName = document.getElementById('Product').value;
    const variant = document.getElementById('Variant').value;
    const unitPrice = document.getElementById('Unit_Price').value;
    const discount = document.getElementById('discount').value;
    const quantity = document.getElementById('Quantity').value;
    const totalAmount = document.getElementById('Total_Amount').value;

    if (productCode && productName && variant && unitPrice && quantity && totalAmount) {
        const table = document.getElementById('productTable').getElementsByTagName('tbody')[0];
        const newRow = table.insertRow();

        const cell1 = newRow.insertCell(0);
        const cell2 = newRow.insertCell(1);
        const cell3 = newRow.insertCell(2);
        const cell4 = newRow.insertCell(3);
        const cell5 = newRow.insertCell(4);
        const cell6 = newRow.insertCell(5);
        const cell7 = newRow.insertCell(6);
        const cell8 = newRow.insertCell(7);

        cell1.innerHTML = `<input type="hidden" name="Product_Code" value="${productCode}">${productCode}`;
        cell2.innerHTML = `<input type="hidden" name="Product" value="${productName}">${productName}`;
        cell3.innerHTML = `<input type="hidden" name="Variant" value="${variant}">${variant}`;
        cell4.innerHTML = `<input type="hidden" name="Unit_Price" value="${unitPrice}">${unitPrice}`;
        cell5.innerHTML = `<input type="hidden" name="discount" value="${discount}">${discount}`;
        cell6.innerHTML = `<input type="hidden" name="Quantity" value="${quantity}">${quantity}`;
        cell7.innerHTML = `<input type="hidden" name="Total_Amount" value="${totalAmount}">${totalAmount}`;
        cell8.innerHTML = '<button type="button" class="btn btn-danger btn-sm" onclick="removeProductRow(this)">Remove</button>';

        updateTotals();

        resetProductFields();
    } else {
        alert('Please fill in all product details before adding.');
    }
}

function removeProductRow(button) {
    const row = button.closest('tr');
    row.remove();
    updateTotals();
}

function updateTotals() {
    let totalAmount = 0;
    let totalDiscount = 0;

    const table = document.getElementById('productTable');
    for (let i = 1, row; row = table.rows[i]; i++) {
        const amount = parseFloat(row.cells[6].innerText) || 0;
        const discount = parseFloat(row.cells[4].innerText) || 0;
        totalAmount += amount;
        totalDiscount += discount;
    }

    document.getElementById('order_amount').value = totalAmount.toFixed(2);
    document.getElementById('total_discount').value = totalDiscount.toFixed(2);
}

function fetchOrderDetails(orderId) {
    fetch(`/get_order_details?order_id=${orderId}`)
        .then(response => response.json())
        .then(data => {
            // Populate the form fields with the order details
            document.getElementById('customer_id').value = data.customer_id;
            document.getElementById('source').value = data.source_id;
            document.getElementById('service_type').value = data.service_id;
            document.getElementById('order_amount').value = data.total_amount;
            document.getElementById('total_discount').value = data.discount;
            document.getElementById('order_status').value = data.status_id;
            document.getElementById('payment_status').value = data.payment_status;

            // Populate product table
            const table = document.getElementById('productTable').getElementsByTagName('tbody')[0];
            table.innerHTML = ''; // Clear existing rows
            data.products.forEach(product => {
                const newRow = table.insertRow();
                newRow.insertCell(0).innerHTML = `<input type="hidden" name="Product_Code" value="${product.product_code}">${product.product_code}`;
                newRow.insertCell(1).innerHTML = `<input type="hidden" name="Product" value="${product.product_name}">${product.product_name}`;
                newRow.insertCell(2).innerHTML = `<input type="hidden" name="Variant" value="${product.variant}">${product.variant}`;
                newRow.insertCell(3).innerHTML = `<input type="hidden" name="Unit_Price" value="${product.unit_price}">${product.unit_price}`;
                newRow.insertCell(4).innerHTML = `<input type="hidden" name="discount" value="${product.discount}">${product.discount}`;
                newRow.insertCell(5).innerHTML = `<input type="hidden" name="Quantity" value="${product.quantity}">${product.quantity}`;
                newRow.insertCell(6).innerHTML = `<input type="hidden" name="Total_Amount" value="${product.total_amount}">${product.total_amount}`;
                newRow.insertCell(7).innerHTML = '<button type="button" class="btn btn-danger btn-sm" onclick="removeProductRow(this)">Remove</button>';
            });

            updateTotals();
        })
        .catch(error => console.error('Error fetching order details:', error));
}

function resetProductFields() {
    document.getElementById('Product_Code').value = '';
    document.getElementById('Product').value = '';
    document.getElementById('Variant').value = '';
    document.getElementById('Unit_Price').value = '';
    document.getElementById('discount').value = '';
    document.getElementById('Quantity').value = '';
    document.getElementById('Total_Amount').value = '';
}
