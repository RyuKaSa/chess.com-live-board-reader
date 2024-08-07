import argparse
from flask import Flask, request, jsonify
from flask_cors import CORS
import chess
import numpy as np
import tensorflow as tf

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

board = chess.Board()

# Argument parsing to choose between modes
parser = argparse.ArgumentParser(description='Chess Prediction Server')
parser.add_argument('mode', choices=['default', 'prediction'], help="Choose 'default' for live board reader only, 'prediction' to use the h5 model")
args = parser.parse_args()

if args.mode == 'prediction':
    # Load the saved model
    model = tf.keras.models.load_model('hikaru_chess_model_v2.h5')

    # Load the move encoder
    move_encoder_keys = np.load('move_encoder_classes_v2.npy', allow_pickle=True)
    move_encoder = {uci: idx for idx, uci in enumerate(move_encoder_keys)}

def update_board(board_state):
    board.clear()
    piece_map = {
        'p': chess.PAWN,
        'r': chess.ROOK,
        'n': chess.KNIGHT,
        'b': chess.BISHOP,
        'q': chess.QUEEN,
        'k': chess.KING
    }

    for item in board_state:
        position = item['position']
        piece_type = item['piece'].lower()
        piece_color = chess.WHITE if item['piece'].isupper() else chess.BLACK
        piece = chess.Piece(piece_map[piece_type], piece_color)
        square = chess.parse_square(position_to_chess_square(position))
        board.set_piece_at(square, piece)

def position_to_chess_square(position):
    file = chr(ord('a') + (int(position) % 10) - 1)
    rank = position[0]
    return f"{file}{rank}"

def board_to_string(board):
    board_string = ""
    for file in range(7, -1, -1):  # Iterate from file 7 (h) to 0 (a) for horizontal flip
        for rank in range(1, 9):  # Iterate from rank 1 to 8 for correct orientation
            square = chess.square(file, rank - 1)
            piece = board.piece_at(square)
            if piece:
                board_string += piece.symbol()
            else:
                board_string += "."
            board_string += " "
        board_string = board_string.strip() + "\n"
    return board_string.strip()

# TensorFlow predictor functions
def board_to_features_from_string(board_str):
    rows = board_str.strip().split("\n")
    features = np.zeros((8, 8, 12), dtype=np.float32)
    
    piece_to_index = {
        'P': 0, 'N': 1, 'B': 2, 'R': 3, 'Q': 4, 'K': 5,
        'p': 6, 'n': 7, 'b': 8, 'r': 9, 'q': 10, 'k': 11,
        '.': None
    }
    
    for row_idx, row in enumerate(rows):
        pieces = row.split()
        for col_idx, piece in enumerate(pieces):
            if piece != '.':
                features[row_idx, col_idx, piece_to_index[piece]] = 1.0
                
    return features

def predict_move_with_tensorflow(board_str, model, move_encoder):
    features = board_to_features_from_string(board_str)
    features = np.expand_dims(features, axis=0)
    preds = model.predict(features)
    sorted_indices = np.argsort(preds[0])[::-1]  # Indices of moves sorted by probability
    
    for move_idx in sorted_indices:
        move_uci = [uci for uci, idx in move_encoder.items() if idx == move_idx][0]
        move = chess.Move.from_uci(move_uci)
        
        # Create a chess board to validate legal moves
        board = chess.Board()
        # Set up the board from the provided board_str
        rows = board_str.strip().split("\n")
        board.clear()
        for row_idx, row in enumerate(rows):
            pieces = row.split()
            for col_idx, piece in enumerate(pieces):
                if piece != '.':
                    piece_type = chess.PIECE_SYMBOLS.index(piece.lower())
                    color = chess.BLACK if piece.islower() else chess.WHITE
                    board.set_piece_at(chess.square(col_idx, 7 - row_idx), chess.Piece(piece_type, color))
        
        if move in board.legal_moves:
            return move
    
    return None  # If no legal move is found

@app.route('/update_board', methods=['POST'])
def update_board_route():
    board_state = request.get_json()
    update_board(board_state)
    string_board = board_to_string(board)
    print("Latest board state:\n" + string_board)
    
    if args.mode == 'prediction':
        # Convert the board string to features
        features = board_to_features_from_string(string_board)
        print(features.shape)  # Should print (8, 8, 12)
        # Predict the move
        predicted_move = predict_move_with_tensorflow(string_board, model, move_encoder)
        print(predicted_move)  # Should print the predicted move in UCI format
        return jsonify({"status": "success", "predicted_move": str(predicted_move)}), 200
    
    return jsonify({"status": "success"}), 200

@app.route('/get_board', methods=['GET'])
def get_board():
    return jsonify({"board": board.fen()}), 200

if __name__ == '__main__':
    app.run(debug=True)