import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts

ApplicationWindow {
    id: window
    visible: true
    width: 900
    height: 600
    minimumWidth: 700
    minimumHeight: 400
    title: "ESPARGOS Demos"
    visibility: backend_fullscreen ? ApplicationWindow.FullScreen : ApplicationWindow.Windowed

    Material.theme: Material.Dark
    Material.accent: Material.Blue

    color: "#222a2f"

    RowLayout {
        anchors.fill: parent
        spacing: 0

        // ── Left panel: common settings ──────────────────────────────────
        Rectangle {
            Layout.preferredWidth: 260
            Layout.fillHeight: true
            color: "#1a2226"

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 20
                spacing: 16

                Label {
                    text: "ESPARGOS Demos"
                    font.pixelSize: 20
                    font.bold: true
                    color: "#ffffff"
                }

                Rectangle {
                    Layout.fillWidth: true
                    height: 1
                    color: "#3a4a54"
                }

                Label {
                    text: "ESPARGOS Unit IP"
                    color: "#9fb3c8"
                    font.pixelSize: 13
                }

                TextField {
                    id: ipField
                    Layout.fillWidth: true
                    placeholderText: "e.g. 192.168.1.2"
                    text: settings.ip
                    color: "#ffffff"
                    background: Rectangle {
                        color: "#2a3a44"
                        radius: 4
                        border.color: ipField.activeFocus ? "#4a9fc8" : "#3a4a54"
                    }
                    onTextChanged: settings.setIp(text)
                }

                RowLayout {
                    Layout.fillWidth: true
                    Label {
                        text: "Single-array mode"
                        color: "#9fb3c8"
                        font.pixelSize: 13
                        Layout.fillWidth: true
                    }
                    Switch {
                        id: singleArraySwitch
                        checked: settings.singleArray
                        onCheckedChanged: settings.setSingleArray(checked)
                    }
                }

                // Status badge
                Rectangle {
                    Layout.fillWidth: true
                    height: 32
                    radius: 6
                    color: settings.ip.length > 0 ? "#1a5c2a" : "#3a2a1a"
                    Label {
                        anchors.centerIn: parent
                        text: settings.ip.length > 0 ? "Ready" : "No IP configured"
                        color: settings.ip.length > 0 ? "#5cdd8b" : "#ddaa55"
                        font.pixelSize: 13
                    }
                }

                Item { Layout.fillHeight: true }  // spacer
            }
        }

        // ── Right panel: demo grid ───────────────────────────────────────
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: "#222a2f"

            GridView {
                id: demoGrid
                objectName: "demoGrid"
                anchors.fill: parent
                anchors.margins: 16
                cellWidth: 224
                cellHeight: 154
                model: scanner.demoItems

                delegate: Item {
                    width: demoGrid.cellWidth
                    height: demoGrid.cellHeight

                    DemoCard {
                        anchors.fill: parent
                        anchors.margins: 8
                        demoName: modelData.name
                        demoDescription: modelData.description
                        combinedArrayOnly: modelData.combined_array_only ?? false
                        singleArrayOnly:   modelData.single_array_only   ?? false
                        disabled:          modelData.disabled             ?? false
                        ip: settings.ip
                        singleArray: settings.singleArray

                        onLaunchRequested: {
                            scanner.launchDemo(index, settings.ip, settings.singleArray, backend_fullscreen)
                        }
                    }
                }
            }
        }
    }

    // Kiosk mode: floating exit button in bottom-right corner
    Button {
        visible: backend_fullscreen
        z: 10
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.margins: 10
        text: "✕ Exit"
        flat: true
        font.pixelSize: 14
        Material.background: "#227b3d"
        Material.foreground: "#ffffffff"
        onClicked: kioskExitDialog.open()
    }

    // Kiosk mode: exit confirmation dialog
    Dialog {
        id: kioskExitDialog
        title: "Exit Application"
        anchors.centerIn: parent
        modal: true
        standardButtons: Dialog.Cancel
        z: 200

        Material.roundedScale: Material.SmallScale

        ColumnLayout {
            spacing: 16
            width: parent.width

            Label {
                text: "What would you like to do?"
                font.pixelSize: 14
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
            }

            Button {
                text: "Quit Application"
                Layout.fillWidth: true
                Material.background: Material.accent
                Material.foreground: "#ffffff"
                onClicked: {
                    kioskExitDialog.close()
                    Qt.quit()
                }
            }

            Button {
                text: "Shut Down Computer"
                Layout.fillWidth: true
                Material.background: "#b71c1c"
                Material.foreground: "#ffffff"
                onClicked: {
                    kioskExitDialog.close()
                    scanner.shutdownComputer()
                }
            }
        }
    }
}
